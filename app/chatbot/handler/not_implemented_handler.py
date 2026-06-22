from __future__ import annotations

from sqlalchemy.orm import Session

from ..types import FragmentStatus
from .base import HandlerResult


class NotImplementedHandler:
  def handle(self, session: Session, text: str) -> HandlerResult:
    return HandlerResult(
      status=FragmentStatus.NOT_IMPLEMENTED,
      slots={},
      result={
        "success": False,
        "reason": "not_implemented",
        "message": "해당 질문 유형은 아직 실행 핸들러가 연결되지 않았습니다.",
      },
    )
