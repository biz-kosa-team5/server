from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session

from app.real_estate.dao import (
  complexes_for_parcel,
  count_trades_for_complex_ids,
  get_complex,
  latest_trade_for_complex,
  monthly_trade_stats,
  trades_for_complex_ids,
)
from app.real_estate.support import clamp, trade_item


def trades_page(
  session: Session,
  parcel_id: int,
  complex_id: int | None,
  complex_ids: list[int],
  page: int,
  size: int,
) -> dict[str, Any]:
  page = max(page, 0)
  size = clamp(size, 1, 100)
  if not complex_ids:
    return {
      "parcelId": parcel_id,
      "complexId": complex_id,
      "content": [],
      "page": page,
      "size": size,
      "totalElements": 0,
      "totalPages": 0,
    }

  total = count_trades_for_complex_ids(session, complex_ids)
  rows = trades_for_complex_ids(session, complex_ids, page, size)
  return {
    "parcelId": parcel_id,
    "complexId": complex_id,
    "content": [trade_item(row) for row in rows],
    "page": page,
    "size": size,
    "totalElements": total,
    "totalPages": math.ceil(total / size) if total else 0,
  }


def trades_by_parcel(
  session: Session,
  parcel_id: int,
  complex_id: int | None,
  page: int,
  size: int,
) -> dict[str, Any]:
  complex_ids = complexes_for_parcel(session, parcel_id, complex_id)
  return trades_page(session, parcel_id, complex_id, complex_ids, page, size)


def trades_by_complex(session: Session, complex_id: int, page: int, size: int) -> dict[str, Any] | None:
  complex_row = get_complex(session, complex_id)
  if complex_row is None:
    return None
  return trades_page(session, complex_row.parcel_id, complex_id, [complex_id], page, size)


def trend_for_complex_ids(session: Session, complex_ids: list[int]) -> list[dict[str, Any]]:
  if not complex_ids:
    return []
  return [
    {
      "month": row.month,
      "avgAmount": round(float(row.avg_amount), 2),
      "count": row.trade_count,
      "minAmount": row.min_amount,
      "maxAmount": row.max_amount,
    }
    for row in monthly_trade_stats(session, complex_ids)
  ]


def trend_by_parcel(session: Session, parcel_id: int, complex_id: int | None) -> list[dict[str, Any]]:
  complex_ids = complexes_for_parcel(session, parcel_id, complex_id)
  return trend_for_complex_ids(session, complex_ids)


def trend_by_complex(session: Session, complex_id: int) -> list[dict[str, Any]] | None:
  if get_complex(session, complex_id) is None:
    return None
  return trend_for_complex_ids(session, [complex_id])


__all__ = [
  "complexes_for_parcel",
  "latest_trade_for_complex",
  "trades_by_complex",
  "trades_by_parcel",
  "trades_page",
  "trend_by_complex",
  "trend_by_parcel",
  "trend_for_complex_ids",
]
