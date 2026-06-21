from __future__ import annotations

import math
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Complex, Trade


def latest_trade_for_complex(session: Session, complex_id: int) -> Trade | None:
  return session.scalar(
    select(Trade)
    .where(Trade.complex_id == complex_id)
    .order_by(Trade.deal_date.desc(), Trade.id.desc())
    .limit(1)
  )


def complexes_for_parcel(session: Session, parcel_id: int, complex_id: int | None) -> list[int]:
  statement = select(Complex.id).where(Complex.parcel_id == parcel_id)
  if complex_id is not None:
    statement = statement.where(Complex.id == complex_id)
  return list(session.scalars(statement).all())


def complex_summary(row: Complex) -> dict[str, Any]:
  return {
    "complexId": row.id,
    "complexName": row.name,
    "parcelId": row.parcel_id,
    "latitude": row.latitude,
    "longitude": row.longitude,
    "address": row.address,
    "dongCnt": row.dong_cnt,
    "unitCnt": row.unit_cnt,
    "useDate": row.use_date,
  }


def complex_detail(row: Complex) -> dict[str, Any]:
  return {
    "parcelId": row.parcel_id,
    "complexId": row.id,
    "latitude": row.latitude,
    "longitude": row.longitude,
    "address": row.address,
    "tradeName": row.trade_name,
    "name": row.name,
    "dongCnt": row.dong_cnt,
    "unitCnt": row.unit_cnt,
    "platArea": None,
    "archArea": None,
    "totArea": None,
    "bcRat": None,
    "vlRat": None,
    "useDate": row.use_date,
  }


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

  total = session.scalar(
    select(func.count()).select_from(Trade).where(Trade.complex_id.in_(complex_ids))
  ) or 0
  rows = session.scalars(
    select(Trade)
    .where(Trade.complex_id.in_(complex_ids))
    .order_by(Trade.deal_date.desc(), Trade.id.desc())
    .limit(size)
    .offset(page * size)
  ).all()
  return {
    "parcelId": parcel_id,
    "complexId": complex_id,
    "content": [trade_item(row) for row in rows],
    "page": page,
    "size": size,
    "totalElements": total,
    "totalPages": math.ceil(total / size) if total else 0,
  }


def trade_item(row: Trade) -> dict[str, Any]:
  return {
    "tradeId": row.id,
    "dealDate": row.deal_date,
    "exclArea": row.excl_area,
    "dealAmount": row.deal_amount,
    "aptDong": row.apt_dong,
    "floor": row.floor,
  }


def trend_for_complex_ids(session: Session, complex_ids: list[int]) -> list[dict[str, Any]]:
  if not complex_ids:
    return []
  month_expr = func.substr(Trade.deal_date, 1, 7)
  rows = session.execute(
    select(
      month_expr.label("month"),
      func.avg(Trade.deal_amount).label("avg_amount"),
      func.count().label("trade_count"),
      func.min(Trade.deal_amount).label("min_amount"),
      func.max(Trade.deal_amount).label("max_amount"),
    )
    .where(Trade.complex_id.in_(complex_ids))
    .group_by(month_expr)
    .order_by("month")
  ).all()
  return [
    {
      "month": row.month,
      "avgAmount": round(float(row.avg_amount), 2),
      "count": row.trade_count,
      "minAmount": row.min_amount,
      "maxAmount": row.max_amount,
    }
    for row in rows
  ]


def optional_float(value: Any) -> float | None:
  if value in (None, ""):
    return None
  return float(value)


def clamp(value: int, minimum: int, maximum: int) -> int:
  return min(max(value, minimum), maximum)
