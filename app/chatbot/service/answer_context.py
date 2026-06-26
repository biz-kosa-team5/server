from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
  from .chatbot_service import ChatbotAnswerContext


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
