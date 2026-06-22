from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.real_estate.service.recommendation_service import recommend_apartments_by_filters


def run_recommendation(session: Session, slots: dict[str, Any], _: str = "") -> dict[str, Any]:
  return recommend_apartments_by_filters(session, slots)
