from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..features.comparison import compare_apartments_by_metrics
from ..features.recommendation import recommend_apartments_by_filters


def handle_query(session: Session, intent: str | None, slots: dict[str, Any]) -> dict[str, Any]:
  # 이 service는 슬롯을 채우지 않는다. 이미 채워진 JSON을 보고 실행할 조회만 고른다.
  intent = clean_text(intent)

  if intent == "recommendation":
    return recommend_apartments_by_filters(session, slots)

  if intent == "comparison":
    return compare_apartments_by_metrics(session, slots)

  return {
    "success": False,
    "reason": "unsupported_intent",
    "message": "지원하지 않는 질문 유형입니다.",
  }


def clean_text(value: Any) -> str | None:
  if value is None:
    return None
  text = str(value).strip()
  if text == "" or text.lower() in {"none", "null"}:
    return None
  return text
