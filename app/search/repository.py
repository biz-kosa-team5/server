from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import Complex


def search_complexes(session: Session, query: str, limit: int = 20) -> list[dict[str, Any]]:
  trimmed = query.strip()
  if not trimmed:
    return []
  pattern = f"%{trimmed}%"
  rows = session.scalars(
    select(Complex)
    .where(or_(Complex.name.like(pattern), Complex.trade_name.like(pattern), Complex.address.like(pattern)))
    .order_by(Complex.name)
    .limit(limit)
  ).all()
  return [complex_search_result(row) for row in rows]


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


def complex_search_result(row: Complex) -> dict[str, Any]:
  return {
    "complexId": row.id,
    "complexName": row.name,
    "parcelId": row.parcel_id,
    "latitude": row.latitude,
    "longitude": row.longitude,
    "address": row.address,
  }
