from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session


def run_unsupported(_: Session, __: dict[str, Any], ___: str = "") -> dict[str, Any]:
  return {
    "success": False,
    "reason": "unsupported_intent",
    "message": "지원하지 않는 질문 유형입니다.",
  }
