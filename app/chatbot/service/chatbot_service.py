from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .dispatcher import dispatch_text
from .handler import fragment_result
from .classifier import classify_intent_with_confidence
from .splitter import split_question


def handle_chatbot_query(session: Session, question: str) -> dict[str, Any]:
  question = question.strip()
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
  classification = classify_intent_with_confidence(text)
  intent = classification.intent
  handler_result = dispatch_text(session, intent, text)
  return fragment_result(
    index,
    text,
    intent,
    handler_result.status,
    handler_result.slots,
    handler_result.result,
    classification.confidence,
  )
