from __future__ import annotations

from sqlalchemy.orm import Session

from ...comparison.extractor import extract_compare_slots
from ...comparison.service import compare_apartments_by_metrics
from ..dto.chatbot_dto import FragmentStatus
from .base import HandlerResult


class ComparisonHandler:
  def handle(self, session: Session, text: str) -> HandlerResult:
    slots = extract_compare_slots(text)
    return HandlerResult(
      status=FragmentStatus.HANDLED,
      slots=slots,
      result=compare_apartments_by_metrics(session, slots),
    )
