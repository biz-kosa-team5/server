from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.real_estate.service.comparison_service import compare_apartments_by_metrics


def run_comparison(session: Session, slots: dict[str, Any], _: str = "") -> dict[str, Any]:
  return compare_apartments_by_metrics(session, slots)
