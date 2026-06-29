"""
기존 chatbot JSON 응답을 최종 답변 생성용 context로 정규화합니다.
LLM에는 answer.observations에서 만든 축약 observation을 전달하고, fallback도 같은 context를 사용합니다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ChatbotAnswerContext:
  question: str
  success: bool
  status: str
  message: str
  fragments: list[dict[str, Any]]
  result: Any
  executionSummary: dict[str, int]
  uiActions: list[dict[str, Any]] = field(default_factory=list)
  uiArtifacts: list[dict[str, Any]] = field(default_factory=list)
  uiSummary: dict[str, Any] | None = None

  @classmethod
  def from_response_dict(cls, response: dict[str, Any]) -> ChatbotAnswerContext:
    fragments = response.get("fragments")
    execution_summary = response.get("executionSummary")
    ui_actions = response.get("uiActions")
    ui_artifacts = response.get("uiArtifacts")
    ui_summary = response.get("uiSummary")
    return cls(
      question=str(response.get("question", "")),
      success=response.get("success") is True,
      status=str(response.get("status", "")),
      message=str(response.get("message", "")),
      fragments=fragments if isinstance(fragments, list) else [],
      result=response.get("result"),
      executionSummary=execution_summary if isinstance(execution_summary, dict) else {},
      uiActions=ui_actions if isinstance(ui_actions, list) else [],
      uiArtifacts=ui_artifacts if isinstance(ui_artifacts, list) else [],
      uiSummary=ui_summary if isinstance(ui_summary, dict) else None,
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
      "uiActions": self.uiActions,
      "uiArtifacts": self.uiArtifacts,
      "uiSummary": self.uiSummary,
    }


def build_llm_context(context: ChatbotAnswerContext) -> dict[str, Any]:
  from .observations import build_answer_observations

  return build_answer_observations(context)


def is_successful_fragment(fragment: dict[str, Any]) -> bool:
  result = fragment.get("result")
  if isinstance(result, dict) and result.get("success") is True:
    return True
  return fragment.get("status") == "handled"
