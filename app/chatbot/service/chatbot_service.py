from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from sqlalchemy.orm import Session

from .answer_composer import ChatbotAnswerComposer
from .supervisor import (
  ChatbotSupervisor,
  agent_execution_failed_result,
  agent_initialization_failed_result,
)
from .splitter import split_question


logger = logging.getLogger(__name__)


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

  @property
  def success(self) -> bool:
    return self.result.get("success") is True

  @property
  def status(self) -> str:
    return "handled" if self.success else "not_handled"

  def to_fragment_dict(self) -> dict[str, Any]:
    return {
      "index": self.task.index,
      "text": self.task.text,
      "status": self.status,
      "result": self.result,
    }


@dataclass(frozen=True)
class TaskExecutionSummary:
  total: int
  succeeded: int
  failed: int

  @classmethod
  def from_task_results(cls, task_results: list[TaskExecutionResult]) -> TaskExecutionSummary:
    total = len(task_results)
    succeeded = sum(1 for task_result in task_results if task_result.success)
    return cls(
      total=total,
      succeeded=succeeded,
      failed=total - succeeded,
    )

  @property
  def success(self) -> bool:
    return self.succeeded > 0

  @property
  def status(self) -> str:
    if self.succeeded == self.total and self.total > 0:
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
class ChatbotAnswerContext:
  question: str
  success: bool
  status: str
  message: str
  fragments: list[dict[str, Any]]
  result: Any
  executionSummary: dict[str, int]

  @classmethod
  def from_response_dict(cls, response: dict[str, Any]) -> ChatbotAnswerContext:
    fragments = response.get("fragments")
    execution_summary = response.get("executionSummary")
    return cls(
      question=str(response.get("question", "")),
      success=response.get("success") is True,
      status=str(response.get("status", "")),
      message=str(response.get("message", "")),
      fragments=fragments if isinstance(fragments, list) else [],
      result=response.get("result"),
      executionSummary=execution_summary if isinstance(execution_summary, dict) else {},
    )

  def to_dict(self) -> dict[str, Any]:
    return {
      "question": self.question,
      "success": self.success,
      "status": self.status,
      "message": self.message,
      "fragments": self.fragments,
      "result": self.result,
      "executionSummary": self.executionSummary,
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
    return {
      "success": summary.success,
      "status": summary.status,
      "question": self.question,
      "fragments": fragments,
      "result": result,
      "message": summary.message,
      "executionSummary": summary.to_dict(),
    }

  def to_answer_context(self, response_dict: dict[str, Any]) -> ChatbotAnswerContext:
    return ChatbotAnswerContext.from_response_dict(response_dict)


async def handle_chatbot_query(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
  question = str(payload.get("question", "")).strip()
  supervisor_initialization_failed = False
  try:
    supervisor = ChatbotSupervisor(session)
  except Exception:
    logger.exception("Failed to initialize chatbot supervisor")
    supervisor = None
    supervisor_initialization_failed = True
  task_results = []
  for task in ChatbotTask.from_question(question):
    task_results.append(await execute_task(
      supervisor,
      task,
      supervisor_initialization_failed=supervisor_initialization_failed,
    ))
  chatbot_response = ChatbotQueryResponse(
    question=question,
    task_results=task_results,
  )
  response_dict = chatbot_response.to_response_dict()
  answer_context = chatbot_response.to_answer_context(response_dict)
  response_dict["answer"] = await ChatbotAnswerComposer().compose(answer_context)
  return response_dict


async def execute_task(
  supervisor: ChatbotSupervisor | None,
  task: ChatbotTask,
  *,
  supervisor_initialization_failed: bool = False,
) -> TaskExecutionResult:
  try:
    if supervisor is None:
      result = (
        agent_initialization_failed_result()
        if supervisor_initialization_failed
        else agent_execution_failed_result()
      )
    else:
      result = await supervisor.run(task.text)
  except Exception:
    logger.exception("Failed to run chatbot supervisor for task %s", task.index)
    result = agent_execution_failed_result()

  return TaskExecutionResult(task=task, result=result)
