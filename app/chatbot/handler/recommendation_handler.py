from __future__ import annotations

from sqlalchemy.orm import Session

from ..flows import recommend_apartments_by_filters
from ..slots import extract_recommendation_slots
from ..types import FragmentStatus
from .base import HandlerResult


class RecommendationHandler:
  def handle(self, session: Session, text: str) -> HandlerResult:
    slots = extract_recommendation_slots(text)
    return HandlerResult(
      status=FragmentStatus.HANDLED,
      slots=slots,
      result=recommend_apartments_by_filters(session, slots),
    )
