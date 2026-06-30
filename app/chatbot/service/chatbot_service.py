"""
챗봇 질문을 fragment로 나누고 Supervisor 실행 결과를 기존 JSON 응답으로 조립합니다.
응답 필드는 유지한 채 최상위 answer만 추가하며, answer 생성 책임은 service.answer 패키지에 위임합니다.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import AsyncIterator
from dataclasses import dataclass
import logging
from typing import Any

from sqlalchemy.orm import Session

from .answer import ChatbotAnswerComposer, ChatbotAnswerContext
from .conversation_memory import (
  build_conversation_memory_patch,
  normalize_conversation_context,
  resolve_contextual_question,
)
from .answer.formatters.sequential import (
  format_dependent_comparison_step_answer,
  format_dependent_recommendation_step_answer,
  format_dependent_sequence_summary,
)
from .orchestrator import (
  OrchestrationResult,
  SequenceStepResult,
  aggregate_sequence_step_results,
  execute_plan,
  iter_recommendation_comparison_sequence,
  requested_comparison_candidate_limit,
)
from .planner import ExecutionPlan, build_execution_plan
from .supervisor import (
  ChatbotSupervisor,
  agent_execution_failed_result,
  agent_initialization_failed_result,
  merge_token_usage,
)
from .splitter import split_question
from .streaming import chunk_answer, format_sse, stream_safe_answer
from .ui_payload import build_chatbot_ui_payload


logger = logging.getLogger(__name__)
STREAM_ERROR_MESSAGE = "AI 집찾기 응답을 불러오지 못했습니다."
STREAM_TOTAL_STEPS = 5
PROGRESSIVE_STREAM_TOTAL_STEPS = 6


class LazySupervisorProvider:
  def __init__(self, session: Session, model: str | None = None):
    self.session = session
    self.model = model
    self.supervisor: ChatbotSupervisor | None = None
    self.attempted = False
    self.initialization_failed = False

  def __call__(self) -> ChatbotSupervisor | None:
    if self.supervisor is not None or self.initialization_failed:
      return self.supervisor
    self.attempted = True
    try:
      self.supervisor = create_chatbot_supervisor(self.session, self.model)
    except Exception:
      logger.exception("Failed to initialize chatbot supervisor")
      self.initialization_failed = True
      self.supervisor = None
    return self.supervisor


@dataclass(frozen=True)
class ChatbotTask:
  index: int
  text: str

  @classmethod
  def from_question(cls, question: str) -> list[ChatbotTask]:
    fragments = split_question(question) or [question]
    return [
      cls(index=index, text=fragment)
      for index, fragment in enumerate(fragments)
    ]


@dataclass(frozen=True)
class TaskExecutionResult:
  task: ChatbotTask
  result: dict[str, Any]
  execution: dict[str, Any] | None = None

  @property
  def success(self) -> bool:
    return self.result.get("success") is True

  @property
  def partial_success(self) -> bool:
    return self.success and self.result.get("status") == "partial_success"

  @property
  def status(self) -> str:
    return "handled" if self.success else "not_handled"

  def to_fragment_dict(self) -> dict[str, Any]:
    fragment = {
      "index": self.task.index,
      "text": self.task.text,
      "status": self.status,
      "result": self.result,
    }
    if self.execution:
      fragment["execution"] = self.execution
    return fragment


@dataclass(frozen=True)
class TaskExecutionSummary:
  total: int
  succeeded: int
  failed: int
  partial_succeeded: int = 0

  @classmethod
  def from_task_results(cls, task_results: list[TaskExecutionResult]) -> TaskExecutionSummary:
    total = len(task_results)
    succeeded = sum(1 for task_result in task_results if task_result.success)
    partial_succeeded = sum(1 for task_result in task_results if task_result.partial_success)
    return cls(
      total=total,
      succeeded=succeeded,
      failed=total - succeeded,
      partial_succeeded=partial_succeeded,
    )

  @property
  def success(self) -> bool:
    return self.succeeded > 0

  @property
  def status(self) -> str:
    if self.succeeded == self.total and self.total > 0 and self.partial_succeeded == 0:
      return "success"
    if self.succeeded > 0:
      return "partial_success"
    return "failed"

  @property
  def message(self) -> str:
    messages = {
      "success": "질문을 처리했습니다.",
      "partial_success": "일부 질문만 처리했습니다.",
      "failed": "처리할 수 있는 질문이 없습니다.",
    }
    return messages[self.status]

  def to_dict(self) -> dict[str, int]:
    return {
      "total": self.total,
      "succeeded": self.succeeded,
      "failed": self.failed,
    }


@dataclass(frozen=True)
class ChatbotQueryResponse:
  question: str
  task_results: list[TaskExecutionResult]

  @property
  def summary(self) -> TaskExecutionSummary:
    return TaskExecutionSummary.from_task_results(self.task_results)

  @property
  def fragments(self) -> list[dict[str, Any]]:
    return [
      task_result.to_fragment_dict()
      for task_result in self.task_results
    ]

  @property
  def results(self) -> list[dict[str, Any]]:
    return [
      task_result.result
      for task_result in self.task_results
    ]

  def to_response_dict(self) -> dict[str, Any]:
    summary = self.summary
    fragments = self.fragments
    results = self.results
    result = results[0] if len(results) == 1 else results
    return strip_nested_answers({
      "success": summary.success,
      "status": summary.status,
      "question": self.question,
      "fragments": fragments,
      "result": result,
      "message": summary.message,
      "executionSummary": summary.to_dict(),
    })

  def to_answer_context(self, response_dict: dict[str, Any]) -> ChatbotAnswerContext:
    return ChatbotAnswerContext.from_response_dict(response_dict)


async def handle_chatbot_query(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
  question = str(payload.get("question", "")).strip()
  conversation_context = normalize_conversation_context(payload.get("conversationContext"))
  resolved_question, conversation_resolution = resolve_contextual_question(
    question,
    conversation_context,
  )
  model = runtime_model_from_payload(payload)
  supervisor_provider = LazySupervisorProvider(session, model=model)
  task_results = []
  for task in ChatbotTask.from_question(resolved_question):
    task_results.append(await execute_task(
      session,
      None,
      task,
      supervisor_provider=supervisor_provider,
    ))
  chatbot_response = ChatbotQueryResponse(
    question=question,
    task_results=task_results,
  )
  response_dict = chatbot_response.to_response_dict()
  response_dict["resolvedQuestion"] = resolved_question
  response_dict["conversationResolution"] = conversation_resolution
  response_dict.update(build_chatbot_ui_payload(session, response_dict))
  answer_context = chatbot_response.to_answer_context(response_dict)
  answer_composer = create_answer_composer(model)
  response_dict["answer"] = await answer_composer.compose(answer_context)
  answer_usage = getattr(answer_composer, "last_usage", None)
  if answer_usage:
    response_dict["answerUsage"] = answer_usage
  usage = collect_response_usage(response_dict)
  if usage:
    response_dict["usage"] = usage
  response_dict["conversationMemoryPatch"] = build_conversation_memory_patch(response_dict)
  return response_dict


async def stream_chatbot_query(session: Session, payload: dict[str, Any]) -> AsyncIterator[bytes]:
  try:
    question = str(payload.get("question", "")).strip()
    model = runtime_model_from_payload(payload)
    tasks = ChatbotTask.from_question(question)
    progressive_plan = progressive_plan_for_tasks(tasks)
    if progressive_plan is not None:
      async for event in stream_recommendation_comparison_sequence(
        session,
        question,
        tasks[0],
        progressive_plan,
      ):
        yield event
      return

    yield stream_status("질문 분석 중", 1)

    yield stream_status("작업 분리 중", 2)
    supervisor_provider = LazySupervisorProvider(session, model=model)
    task_results = []
    task_count = len(tasks)
    for task_number, task in enumerate(tasks, start=1):
      yield stream_status(f"작업 {task_number}/{task_count} 처리 중", 3)
      task_results.append(await execute_task(
        session,
        None,
        task,
        supervisor_provider=supervisor_provider,
      ))

    chatbot_response = ChatbotQueryResponse(
      question=question,
      task_results=task_results,
    )
    response_dict = chatbot_response.to_response_dict()

    yield stream_status("지도/시각 자료 준비 중", 4)
    ui_payload = build_chatbot_ui_payload(session, response_dict)
    response_dict.update(ui_payload)
    yield stream_status("답변 문장 정리 중", 5)
    yield format_sse("artifacts", ui_payload)

    answer_context = chatbot_response.to_answer_context(response_dict)
    answer_composer = create_answer_composer(model)
    response_dict["answer"] = await answer_composer.compose(answer_context)
    answer_usage = getattr(answer_composer, "last_usage", None)
    if answer_usage:
      response_dict["answerUsage"] = answer_usage
    usage = collect_response_usage(response_dict)
    if usage:
      response_dict["usage"] = usage

    for text in chunk_answer(response_dict.get("answer") or response_dict.get("message") or ""):
      yield format_sse("answer_delta", {"text": text})
    yield format_sse("final", response_dict)
  except Exception:
    logger.exception("Failed to stream chatbot query")
    yield format_sse("error", {"message": STREAM_ERROR_MESSAGE})


async def stream_recommendation_comparison_sequence(
  session: Session,
  question: str,
  task: ChatbotTask,
  plan: ExecutionPlan,
) -> AsyncIterator[bytes]:
  yield stream_status("질문 의도 파악 중", 1, total=PROGRESSIVE_STREAM_TOTAL_STEPS)
  yield stream_status("처리 순서 정하는 중", 2, total=PROGRESSIVE_STREAM_TOTAL_STEPS)

  streamed_answer_parts: list[str] = []
  sequence: list[SequenceStepResult] = []
  sequence_iterator = iter(iter_recommendation_comparison_sequence(session, task.text, plan))

  yield stream_status("추천 후보 찾는 중", 3, total=PROGRESSIVE_STREAM_TOTAL_STEPS)
  try:
    recommendation_step = next(sequence_iterator)
  except StopIteration:
    recommendation_step = None

  if recommendation_step is not None:
    sequence.append(recommendation_step)
    recommendation_answer = format_dependent_recommendation_step_answer(
      recommendation_step.result,
      max_candidates=requested_comparison_candidate_limit(task.text),
    )
    for event in stream_answer_delta(recommendation_answer, streamed_answer_parts):
      yield event

  comparison_step = None
  yield stream_status("추천 후보 비교 중", 4, total=PROGRESSIVE_STREAM_TOTAL_STEPS)
  try:
    comparison_step = next(sequence_iterator)
  except StopIteration:
    comparison_step = None

  if comparison_step is not None:
    sequence.append(comparison_step)
    recommendation_result = recommendation_step.result if recommendation_step is not None else None
    comparison_answer = format_dependent_comparison_step_answer(
      comparison_step.result,
      recommendation_result,
    )
    for event in stream_answer_delta(comparison_answer, streamed_answer_parts):
      yield event

  yield stream_status("최종 답변 정리 중", 5, total=PROGRESSIVE_STREAM_TOTAL_STEPS)
  if recommendation_step is not None and comparison_step is not None:
    summary = format_dependent_sequence_summary(
      recommendation_step.result,
      comparison_step.result,
    )
    for event in stream_answer_delta(summary, streamed_answer_parts):
      yield event

  orchestration = aggregate_sequence_step_results(sequence, plan)
  execution = enrich_execution_trace(orchestration.execution, orchestration.result)
  chatbot_response = ChatbotQueryResponse(
    question=question,
    task_results=[
      TaskExecutionResult(
        task=task,
        result=orchestration.result,
        execution=execution,
      )
    ],
  )
  response_dict = chatbot_response.to_response_dict()

  yield stream_status("지도/시각 자료 준비 중", 6, total=PROGRESSIVE_STREAM_TOTAL_STEPS)
  ui_payload = build_chatbot_ui_payload(session, response_dict)
  response_dict.update(ui_payload)
  yield format_sse("artifacts", ui_payload)

  response_dict["answer"] = "".join(streamed_answer_parts).strip() or response_dict.get("message") or "질문을 처리했습니다."
  usage = collect_response_usage(response_dict)
  if usage:
    response_dict["usage"] = usage
  yield format_sse("final", response_dict)


def stream_answer_delta(answer: str, streamed_answer_parts: list[str]) -> list[bytes]:
  safe_answer = stream_safe_answer(answer)
  if not safe_answer:
    return []
  prefix = "\n\n" if streamed_answer_parts else ""
  if streamed_answer_parts:
    safe_answer = f"\n\n{safe_answer}"
  streamed_answer_parts.append(safe_answer)
  chunks = chunk_answer(safe_answer.removeprefix(prefix))
  if prefix and chunks:
    chunks[0] = f"{prefix}{chunks[0]}"
  return [
    format_sse("answer_delta", {"text": chunk})
    for chunk in chunks
  ]


def progressive_plan_for_tasks(tasks: list[ChatbotTask]) -> ExecutionPlan | None:
  if len(tasks) != 1:
    return None
  plan = build_execution_plan(tasks[0].text)
  if is_recommendation_comparison_sequence_plan(plan):
    return plan
  return None


def is_recommendation_comparison_sequence_plan(plan: ExecutionPlan) -> bool:
  return (
    plan.plan_type == "dependent_multi_feature"
    and len(plan.steps) >= 2
    and [step.handler for step in plan.steps[:2]] == ["recommendation", "comparison"]
    and plan.steps[1].depends_on == "recommendation_agent"
  )


def stream_status(label: str, step: int, *, total: int = STREAM_TOTAL_STEPS) -> bytes:
  return format_sse(
    "status",
    {
      "label": label,
      "step": step,
      "total": total,
    },
  )


def create_chatbot_supervisor(session: Session, model: str | None) -> ChatbotSupervisor:
  if model is None:
    return ChatbotSupervisor(session)
  try:
    return ChatbotSupervisor(session, model=model)
  except TypeError as exc:
    if "unexpected keyword argument 'model'" not in str(exc):
      raise
    return ChatbotSupervisor(session)


def create_answer_composer(model: str | None) -> ChatbotAnswerComposer:
  if model is None:
    return ChatbotAnswerComposer()
  try:
    return ChatbotAnswerComposer(model=model)
  except TypeError as exc:
    if "unexpected keyword argument 'model'" not in str(exc):
      raise
    return ChatbotAnswerComposer()


def runtime_model_from_payload(payload: dict[str, Any]) -> str | None:
  for key in ("model", "chat_model", "chatModel"):
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
      return value.strip()
  return None


def collect_response_usage(response_dict: dict[str, Any]) -> dict[str, int] | None:
  usages = []
  for execution in fragment_executions_from_response(response_dict):
    usage = execution.get("usage")
    if isinstance(usage, dict):
      usages.append(usage)
  answer_usage = response_dict.get("answerUsage")
  if isinstance(answer_usage, dict):
    usages.append(answer_usage)
  return merge_token_usage(*usages)


def fragment_executions_from_response(response_dict: dict[str, Any]) -> list[dict[str, Any]]:
  fragments = response_dict.get("fragments")
  if not isinstance(fragments, list):
    return []
  executions = []
  for fragment in fragments:
    if not isinstance(fragment, dict):
      continue
    execution = fragment.get("execution")
    if isinstance(execution, dict):
      executions.append(execution)
  return executions


async def execute_task(
  session: Session,
  supervisor: ChatbotSupervisor | None,
  task: ChatbotTask,
  *,
  supervisor_provider: LazySupervisorProvider | None = None,
  supervisor_initialization_failed: bool = False,
) -> TaskExecutionResult:
  execution: dict[str, Any] | None = None
  try:
    plan = None

    def fallback_plan():
      nonlocal plan
      if plan is None:
        plan = build_execution_plan(task.text)
      return plan

    result, execution = await run_supervisor_first(
      task.text,
      supervisor,
      supervisor_provider=supervisor_provider,
      supervisor_initialization_failed=supervisor_initialization_failed,
    )
    fallback_reason = direct_fallback_reason(result, execution, fallback_plan())
    if fallback_reason:
      orchestration_result = await run_direct_fallback(
        session,
        task.text,
        fallback_plan(),
        fallback_reason=fallback_reason,
      )
      if orchestration_result is not None:
        result = orchestration_result.result
        execution = orchestration_result.execution

    if execution is not None and "planType" not in execution:
      execution = {
        **execution,
        "planType": fallback_plan().plan_type,
      }
  except Exception:
    logger.exception("Failed to run chatbot task %s", task.index)
    result = agent_execution_failed_result()
    execution = {"path": "supervisor_execution_failed"}

  return TaskExecutionResult(task=task, result=result, execution=execution)


async def run_supervisor_first(
  text: str,
  supervisor: ChatbotSupervisor | None,
  *,
  supervisor_provider: LazySupervisorProvider | None,
  supervisor_initialization_failed: bool,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
  if supervisor is None and supervisor_provider is not None:
    supervisor = supervisor_provider()
    supervisor_initialization_failed = (
      supervisor_initialization_failed
      or supervisor_provider.initialization_failed
    )

  if supervisor is None:
    result = (
      agent_initialization_failed_result()
      if supervisor_initialization_failed
      else agent_execution_failed_result()
    )
    execution = {
      "path": "supervisor_initialization_failed"
      if supervisor_initialization_failed
      else "supervisor_unavailable",
    }
    return result, execution

  try:
    run_with_trace = getattr(supervisor, "run_with_trace", None)
    if callable(run_with_trace):
      result, execution = await run_with_trace(text)
      if execution is not None:
        execution = enrich_execution_trace(execution, result)
    else:
      result = await supervisor.run(text)
      execution = None
    if execution is None:
      execution = infer_supervisor_execution(result)
    return result, execution
  except Exception:
    logger.exception("Failed to run chatbot supervisor")
    return agent_execution_failed_result(), {"path": "supervisor_execution_failed"}


async def run_direct_fallback(
  session: Session,
  text: str,
  plan: ExecutionPlan,
  *,
  fallback_reason: str,
) -> OrchestrationResult | None:
  try:
    orchestration_result = await execute_plan(
      session,
      text,
      plan,
      supervisor=None,
      supervisor_provider=None,
      supervisor_initialization_failed=False,
      allow_lookup_trend_direct=True,
    )
  except Exception:
    logger.exception("Failed to run direct chatbot fallback")
    return None

  if orchestration_result is None:
    return None

  execution = enrich_execution_trace(
    orchestration_result.execution,
    orchestration_result.result,
  )
  return OrchestrationResult(
    result=orchestration_result.result,
    execution={
      **execution,
      "fallbackFrom": "supervisor",
      "fallbackReason": fallback_reason,
    },
  )


def direct_fallback_reason(
  result: dict[str, Any],
  execution: dict[str, Any] | None,
  plan: ExecutionPlan | None,
) -> str | None:
  path = execution.get("path") if execution else None
  if path in {
    "supervisor_no_tool",
    "supervisor_unavailable",
    "supervisor_initialization_failed",
    "supervisor_execution_failed",
  }:
    return str(path)

  if plan is not None and missing_required_handlers(result, execution, plan):
    return "supervisor_missing_required_handlers"

  return None


def missing_required_handlers(
  result: dict[str, Any],
  execution: dict[str, Any] | None,
  plan: ExecutionPlan,
) -> list[str]:
  if plan.plan_type not in {
    "independent_multi_feature",
    "dependent_multi_feature",
    "ambiguous_multi_feature",
    "same_tool_multi_feature",
  }:
    return []

  expected = Counter(
    step.handler
    for step in plan.steps
    if step.handler != "no_matching_tool"
  )
  if not expected:
    return []

  actual = Counter(actual_handler_calls(result, execution))
  missing = []
  for handler, count in expected.items():
    missing.extend([handler] * max(0, count - actual.get(handler, 0)))
  return missing


def actual_handler_calls(
  result: dict[str, Any],
  execution: dict[str, Any] | None,
) -> list[str]:
  handler_calls = handler_calls_from_result(result)
  if handler_calls:
    return handler_calls
  if not execution:
    return []
  execution_handler_calls = execution.get("handlerCalls")
  if isinstance(execution_handler_calls, list):
    return [
      str(handler)
      for handler in execution_handler_calls
      if handler
    ]
  execution_handlers = execution.get("handlers")
  if isinstance(execution_handlers, list):
    return [
      str(handler)
      for handler in execution_handlers
      if handler
    ]
  handler = execution.get("handler")
  return [str(handler)] if isinstance(handler, str) else []


def infer_supervisor_execution(result: dict[str, Any]) -> dict[str, Any]:
  reason = result.get("reason")
  if reason == "no_matching_tool":
    return {"path": "supervisor_no_tool"}
  if reason == "agent_execution_failed":
    return {"path": "supervisor_execution_failed"}
  if reason == "agent_initialization_failed":
    return {"path": "supervisor_initialization_failed"}
  if isinstance(result.get("results"), list):
    return enrich_execution_trace(
      {
        "path": "supervisor_aggregate",
        "selectedAgents": selected_agents_from_result(result),
      },
      result,
    )
  return enrich_execution_trace(
    {
      "path": "specialist_tool",
      "selectedAgent": agent_for_handler(result.get("handler")),
    },
    result,
  )


def enrich_execution_trace(trace: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
  enriched = {
    key: item
    for key, item in trace.items()
    if item or item == 0
  }
  handler = first_handler(result)
  handlers = handlers_from_result(result)
  handler_calls = handler_calls_from_result(result)
  if handler:
    enriched["handler"] = handler
  if len(handlers) > 1:
    enriched["handlers"] = handlers
  if len(handler_calls) > 1:
    enriched["handlerCalls"] = handler_calls
  selected_agents = selected_agents_from_result(result)
  if selected_agents and "selectedAgents" not in enriched and "selectedAgent" not in enriched:
    if len(selected_agents) == 1:
      enriched["selectedAgent"] = selected_agents[0]
    else:
      enriched["selectedAgents"] = selected_agents
  return enriched


def agent_for_handler(handler: Any) -> str | None:
  return {
    "simple_lookup": "lookup_agent",
    "price_trend": "price_trend_agent",
    "recommendation": "recommendation_agent",
    "comparison": "comparison_agent",
    "legal_contract": "legal_contract_agent",
  }.get(handler)


def first_handler(result: Any) -> str | None:
  handlers = handlers_from_result(result)
  return handlers[0] if handlers else None


def handlers_from_result(result: Any) -> list[str]:
  handlers: list[str] = []

  def visit(value: Any) -> None:
    if isinstance(value, list):
      for item in value:
        visit(item)
      return
    if not isinstance(value, dict):
      return
    handler = value.get("handler")
    if isinstance(handler, str) and handler not in handlers:
      handlers.append(handler)
    if "result" in value:
      visit(value.get("result"))
    if "results" in value:
      visit(value.get("results"))

  visit(result)
  return handlers


def handler_calls_from_result(result: Any) -> list[str]:
  handlers: list[str] = []

  def visit(value: Any) -> None:
    if isinstance(value, list):
      for item in value:
        visit(item)
      return
    if not isinstance(value, dict):
      return
    handler = value.get("handler")
    if isinstance(handler, str):
      handlers.append(handler)
    if "result" in value:
      visit(value.get("result"))
    if "results" in value:
      visit(value.get("results"))

  visit(result)
  return handlers


def selected_agents_from_result(result: Any) -> list[str]:
  agents: list[str] = []

  def visit(value: Any) -> None:
    if isinstance(value, list):
      for item in value:
        visit(item)
      return
    if not isinstance(value, dict):
      return
    agent = value.get("agent")
    if isinstance(agent, str) and agent not in agents:
      agents.append(agent)
    if "result" in value:
      visit(value.get("result"))
    if "results" in value:
      visit(value.get("results"))

  visit(result)
  return agents


def strip_nested_answers(value: Any) -> Any:
  if isinstance(value, list):
    return [strip_nested_answers(item) for item in value]
  if isinstance(value, dict):
    return {
      key: strip_nested_answers(item)
      for key, item in value.items()
      if key != "answer"
    }
  return value
