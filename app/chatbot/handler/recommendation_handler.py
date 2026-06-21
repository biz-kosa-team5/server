from __future__ import annotations

from sqlalchemy.orm import Session

from ...recommendation.extractor import extract_recommendation_slots
from ...recommendation.service import recommend_apartments_by_filters
from ..dto.chatbot_dto import FragmentStatus
from .base import HandlerResult


class RecommendationHandler:
  def handle(self, session: Session, text: str) -> HandlerResult:
    slots = extract_recommendation_slots(text)
    return HandlerResult(
      status=FragmentStatus.HANDLED,
      slots=slots,
      result=recommend_apartments_by_filters(session, slots),
    )
