from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ...comparison.extractor import extract_compare_slots
from ...comparison.service import compare_apartments_by_metrics
from ...recommendation.extractor import extract_recommendation_slots
from ...recommendation.service import recommend_apartments_by_filters
from ..dto.chatbot_dto import ChatbotQueryRequest, FragmentStatus, Intent
from .classifier import classify_intent
from .splitter import split_question


def handle_chatbot_query(session: Session, payload: ChatbotQueryRequest) -> dict[str, Any]:
  question = payload.question.strip()
  fragments = [
    handle_fragment(session, index, fragment)
    for index, fragment in enumerate(split_question(question) or [question])
  ]
  results = [fragment["result"] for fragment in fragments]
  success = any(result.get("success") is True for result in results)

  return {
    "success": success,
    "question": question,
    "fragments": fragments,
    "result": results[0] if len(results) == 1 else results,
    "message": "질문을 처리했습니다." if success else "처리할 수 있는 질문이 없습니다.",
  }


def handle_fragment(session: Session, index: int, text: str) -> dict[str, Any]:
  intent = classify_intent(text)

  if intent == Intent.RECOMMENDATION:
    slots = extract_recommendation_slots(text)
    return fragment_result(
      index,
      text,
      intent,
      FragmentStatus.HANDLED,
      slots,
      recommend_apartments_by_filters(session, slots),
    )

  if intent == Intent.COMPARISON:
    slots = extract_compare_slots(text)
    return fragment_result(
      index,
      text,
      intent,
      FragmentStatus.HANDLED,
      slots,
      compare_apartments_by_metrics(session, slots),
    )

  if intent in {Intent.SIMPLE_LOOKUP, Intent.PRICE_TREND, Intent.LEGAL_CONTRACT}:
    return fragment_result(
      index,
      text,
      intent,
      FragmentStatus.NOT_IMPLEMENTED,
      {},
      {
        "success": False,
        "reason": "not_implemented",
        "message": "해당 질문 유형은 아직 실행 핸들러가 연결되지 않았습니다.",
      },
    )

  return fragment_result(
    index,
    text,
    intent,
    FragmentStatus.UNSUPPORTED,
    {},
    {
      "success": False,
      "reason": "unsupported_intent",
      "message": "지원하지 않는 질문 유형입니다.",
    },
  )


def fragment_result(
  index: int,
  text: str,
  intent: Intent,
  status: FragmentStatus,
  slots: dict[str, Any],
  result: dict[str, Any],
) -> dict[str, Any]:
  return {
    "index": index,
    "text": text,
    "intent": intent.value,
    "status": status.value,
    "confidence": None,
    "slots": slots,
    "result": result,
  }

