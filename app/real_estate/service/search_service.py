from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.real_estate.dao import search_complexes_by_text
from app.real_estate.support import complex_search_result


def search_complexes(session: Session, query: str, limit: int = 20) -> list[dict[str, Any]]:
  trimmed = query.strip()
  if not trimmed:
    return []
  return [complex_search_result(row) for row in search_complexes_by_text(session, trimmed, limit)]


def search_suggestions(session: Session, query: str) -> list[dict[str, Any]]:
  return [
    {
      "complexId": item["complexId"],
      "complexName": item["complexName"],
      "parcelId": item["parcelId"],
      "address": item["address"],
    }
    for item in search_complexes(session, query, limit=10)
  ]
