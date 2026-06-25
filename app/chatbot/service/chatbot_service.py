from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from sqlalchemy.orm import Session

from .agent import (
  ChatbotAgent,
  agent_execution_failed_result,
  agent_initialization_failed_result,
)
from .splitter import split_question


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FragmentExecutionSummary:
  total: int
  succeeded: int
  failed: int

  @classmethod
  def from_results(cls, results: list[dict[str, Any]]) -> FragmentExecutionSummary:
    total = len(results)
    succeeded = sum(1 for result in results if result.get("success") is True)
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


async def handle_chatbot_query(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
  question = str(payload.get("question", "")).strip()
  agent_initialization_failed = False
  try:
    agent = ChatbotAgent(session)
  except Exception:
    logger.exception("Failed to initialize chatbot agent")
    agent = None
    agent_initialization_failed = True
  fragments = []
  for index, fragment in enumerate(split_question(question) or [question]):
    fragments.append(await handle_fragment(
      agent,
      index,
      fragment,
      agent_initialization_failed=agent_initialization_failed,
    ))
  results = [fragment["result"] for fragment in fragments]
  summary = FragmentExecutionSummary.from_results(results)

  return {
    "success": summary.success,
    "status": summary.status,
    "question": question,
    "fragments": fragments,
    "result": results[0] if len(results) == 1 else results,
    "message": summary.message,
    "executionSummary": summary.to_dict(),
  }


async def handle_fragment(
  agent: ChatbotAgent | None,
  index: int,
  text: str,
  *,
  agent_initialization_failed: bool = False,
) -> dict[str, Any]:
  try:
    if agent is None:
      result = (
        agent_initialization_failed_result()
        if agent_initialization_failed
        else agent_execution_failed_result()
      )
    else:
      result = await agent.run(text)
  except Exception:
    logger.exception("Failed to run chatbot agent for fragment %s", index)
    result = agent_execution_failed_result()

  return {
    "index": index,
    "text": text,
    "status": "handled" if result.get("success") is True else "not_handled",
    "result": result,
  }
