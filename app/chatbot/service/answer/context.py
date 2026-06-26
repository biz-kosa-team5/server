"""
기존 chatbot JSON 응답을 최종 답변 생성용 context로 정규화합니다.
LLM에는 원본 응답과 성공/실패 fragment 구분을 함께 전달하고, fallback도 같은 구조를 사용합니다.
"""
from __future__ import annotations

from dataclasses import dataclass
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


def build_llm_context(context: ChatbotAnswerContext) -> dict[str, Any]:
  successful_fragments = [
    fragment
    for fragment in context.fragments
    if is_successful_fragment(fragment)
  ]
  failed_fragments = [
    fragment
    for fragment in context.fragments
    if not is_successful_fragment(fragment)
  ]
  result_shape = "multiple" if isinstance(context.result, list) else "single"

  return {
    "question": context.question,
    "success": context.success,
    "status": context.status,
    "message": context.message,
    "executionSummary": context.executionSummary,
    "resultShape": result_shape,
    "successfulFragments": successful_fragments,
    "failedFragments": failed_fragments,
    "singleResult": context.result if result_shape == "single" else None,
    "multipleResults": context.result if result_shape == "multiple" else [],
    "rawResponse": context.to_dict(),
  }


def is_successful_fragment(fragment: dict[str, Any]) -> bool:
  result = fragment.get("result")
  if isinstance(result, dict) and result.get("success") is True:
    return True
  return fragment.get("status") == "handled"
