from __future__ import annotations

from sqlalchemy.orm import Session

from ...handler.base import HandlerResult
from ...types import FragmentStatus


class UnsupportedHandler:
  def handle(self, session: Session, text: str) -> HandlerResult:
    return HandlerResult(
      status=FragmentStatus.UNSUPPORTED,
      slots={},
      result={
        "success": False,
        "reason": "unsupported_intent",
        "message": "지원하지 않는 질문 유형입니다.",
      },
    )
