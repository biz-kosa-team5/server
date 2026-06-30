"""
챗봇 질문을 fragment로 나누고 Supervisor 실행 결과를 기존 JSON 응답으로 조립합니다.
응답 필드는 유지한 채 최상위 answer만 추가하며, answer 생성 책임은 service.answer 패키지에 위임합니다.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from sqlalchemy.orm import Session

from .answer import ChatbotAnswerComposer, ChatbotAnswerContext
from .orchestrator import OrchestrationResult, execute_plan
from .planner import ExecutionPlan, build_execution_plan
from .supervisor import (
  ChatbotSupervisor,
  agent_execution_failed_result,
  agent_initialization_failed_result,
)
from .splitter import split_question
from .ui_payload import build_chatbot_ui_payload


logger = logging.getLogger(__name__)


class LazySupervisorProvider:
  def __init__(self, session: Session):
    self.session = session
    self.supervisor: ChatbotSupervisor | None = None
    self.attempted = False
    self.initialization_failed = False

  def __call__(self) -> ChatbotSupervisor | None:
    if self.supervisor is not None or self.initialization_failed:
      return self.supervisor
    self.attempted = True
    try:
      self.supervisor = ChatbotSupervisor(self.session)
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
  supervisor_provider = LazySupervisorProvider(session)
  task_results = []
  for task in ChatbotTask.from_question(question):
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
  response_dict.update(build_chatbot_ui_payload(session, response_dict))
  answer_context = chatbot_response.to_answer_context(response_dict)
  response_dict["answer"] = await ChatbotAnswerComposer().compose(answer_context)
  return response_dict


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
    if should_run_direct_fallback(result, execution):
      orchestration_result = await run_direct_fallback(
        session,
        task.text,
        fallback_plan(),
        fallback_reason=fallback_reason_from_supervisor(result, execution),
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


def should_run_direct_fallback(
  result: dict[str, Any],
  execution: dict[str, Any] | None,
) -> bool:
  path = execution.get("path") if execution else None
  return path in {
    "supervisor_no_tool",
    "supervisor_unavailable",
    "supervisor_initialization_failed",
    "supervisor_execution_failed",
  }


def fallback_reason_from_supervisor(
  result: dict[str, Any],
  execution: dict[str, Any] | None,
) -> str:
  if execution and execution.get("path"):
    return str(execution["path"])
  if result.get("reason"):
    return str(result["reason"])
  return "supervisor_unhandled"


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
