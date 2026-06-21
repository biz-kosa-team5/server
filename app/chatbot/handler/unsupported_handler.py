from __future__ import annotations

from sqlalchemy.orm import Session

from ..dto.chatbot_dto import FragmentStatus
from .base import HandlerResult


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
