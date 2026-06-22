from __future__ import annotations

from sqlalchemy.orm import Session

from ...handler.base import HandlerResult
from ...types import FragmentStatus
from .flow import compare_apartments_by_metrics
from .slots import extract_compare_slots


class ComparisonHandler:
  def handle(self, session: Session, text: str) -> HandlerResult:
    slots = extract_compare_slots(text)
    return HandlerResult(
      status=FragmentStatus.HANDLED,
      slots=slots,
      result=compare_apartments_by_metrics(session, slots),
    )
