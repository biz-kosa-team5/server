from __future__ import annotations

import math
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .models import Complex, Region, Trade

DEFAULT_BOUNDS = {
  "swLat": 37.40,
  "swLng": 126.90,
  "neLat": 37.60,
  "neLng": 127.20,
}


def health() -> dict[str, str]:
  return {"status": "ok"}


def region_markers(session: Session, payload: dict[str, Any]) -> list[dict[str, Any]]:
  bounds = bounds_from_payload(payload)
  rows = session.scalars(
    select(Region)
    .where(Region.center_lat.between(bounds["swLat"], bounds["neLat"]))
    .where(Region.center_lng.between(bounds["swLng"], bounds["neLng"]))
    .order_by(Region.name)
  ).all()
  return [
    {
      "id": row.id,
      "name": row.name,
      "lat": row.center_lat,
      "lng": row.center_lng,
      "unitCntSum": row.unit_cnt_sum,
    }
    for row in rows
  ]


def complex_markers(session: Session, payload: dict[str, Any]) -> list[dict[str, Any]]:
  bounds = bounds_from_payload(payload)
  rows = session.scalars(
    select(Complex)
    .where(Complex.latitude.is_not(None))
    .where(Complex.longitude.is_not(None))
    .where(Complex.latitude.between(bounds["swLat"], bounds["neLat"]))
    .where(Complex.longitude.between(bounds["swLng"], bounds["neLng"]))
    .order_by(Complex.name)
  ).all()
  return [
    marker
    for row in rows
    if (marker := complex_marker(session, row, payload)) is not None
  ]


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


def root_regions(session: Session) -> list[dict[str, Any]]:
  rows = session.scalars(
    select(Region).where(Region.parent_id.is_(None)).order_by(Region.name)
  ).all()
  return [{"id": row.id, "name": row.name} for row in rows]


def region_detail(session: Session, region_id: int) -> dict[str, Any] | None:
  row = session.get(Region, region_id)
  if row is None:
    return None

  children = session.scalars(
    select(Region).where(Region.parent_id == region_id).order_by(Region.name)
  ).all()
  return {
    "id": row.id,
    "name": row.name,
    "latitude": row.center_lat,
    "longitude": row.center_lng,
    "children": [{"id": child.id, "name": child.name} for child in children],
  }


def region_complexes(session: Session, region_id: int, limit: int, offset: int) -> list[dict[str, Any]]:
  rows = session.scalars(
    select(Complex)
    .where(Complex.region_id == region_id)
    .order_by(Complex.name)
    .limit(clamp(limit, 1, 100))
    .offset(max(offset, 0))
  ).all()
  return [complex_summary(row) for row in rows]


def detail_by_parcel(
  session: Session,
  parcel_id: int,
  complex_id: int | None = None,
) -> dict[str, Any] | None:
  statement = select(Complex).where(Complex.parcel_id == parcel_id).order_by(Complex.id).limit(1)
  if complex_id is not None:
    statement = select(Complex).where(Complex.parcel_id == parcel_id, Complex.id == complex_id)
  row = session.scalar(statement)
  return None if row is None else complex_detail(row)


def detail_by_complex(session: Session, complex_id: int) -> dict[str, Any] | None:
  row = session.get(Complex, complex_id)
  return None if row is None else complex_detail(row)


def parcel_complexes(session: Session, parcel_id: int) -> list[dict[str, Any]]:
  rows = session.scalars(
    select(Complex).where(Complex.parcel_id == parcel_id).order_by(Complex.name)
  ).all()
  return [complex_summary(row) for row in rows]


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
  complex_row = session.get(Complex, complex_id)
  if complex_row is None:
    return None
  return trades_page(session, complex_row.parcel_id, complex_id, [complex_id], page, size)


def trend_by_parcel(session: Session, parcel_id: int, complex_id: int | None) -> list[dict[str, Any]]:
  complex_ids = complexes_for_parcel(session, parcel_id, complex_id)
  return trend_for_complex_ids(session, complex_ids)


def trend_by_complex(session: Session, complex_id: int) -> list[dict[str, Any]] | None:
  if session.get(Complex, complex_id) is None:
    return None
  return trend_for_complex_ids(session, [complex_id])


def bounds_from_payload(payload: dict[str, Any]) -> dict[str, float]:
  source = payload.get("bounds") if isinstance(payload.get("bounds"), dict) else payload
  return {
    key: float(source.get(key, fallback))
    for key, fallback in DEFAULT_BOUNDS.items()
  }


def complex_marker(session: Session, row: Complex, filters: dict[str, Any]) -> dict[str, Any] | None:
  latest_trade = latest_trade_for_complex(session, row.id)
  if not matches_filters(row, latest_trade, filters):
    return None
  return {
    "parcelId": row.parcel_id,
    "complexId": row.id,
    "name": row.name,
    "lat": row.latitude,
    "lng": row.longitude,
    "latestDealAmount": None if latest_trade is None else latest_trade.deal_amount,
    "unitCntSum": row.unit_cnt,
  }


def matches_filters(row: Complex, latest_trade: Trade | None, filters: dict[str, Any]) -> bool:
  if not number_between(row.unit_cnt, filters.get("unitMin"), filters.get("unitMax")):
    return False

  age = age_from_use_date(row.use_date)
  if age is not None and not number_between(age, filters.get("ageMin"), filters.get("ageMax")):
    return False

  if latest_trade is None:
    return filters.get("priceEokMin") in (None, "") and filters.get("priceEokMax") in (None, "")

  price_eok = latest_trade.deal_amount / 10000
  area_pyeong = latest_trade.excl_area / 3.3058
  return (
    number_between(price_eok, filters.get("priceEokMin"), filters.get("priceEokMax"))
    and number_between(area_pyeong, filters.get("pyeongMin"), filters.get("pyeongMax"))
  )


def latest_trade_for_complex(session: Session, complex_id: int) -> Trade | None:
  return session.scalar(
    select(Trade)
    .where(Trade.complex_id == complex_id)
    .order_by(Trade.deal_date.desc(), Trade.id.desc())
    .limit(1)
  )


def complex_search_result(row: Complex) -> dict[str, Any]:
  return {
    "complexId": row.id,
    "complexName": row.name,
    "parcelId": row.parcel_id,
    "latitude": row.latitude,
    "longitude": row.longitude,
    "address": row.address,
  }


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


def complexes_for_parcel(session: Session, parcel_id: int, complex_id: int | None) -> list[int]:
  statement = select(Complex.id).where(Complex.parcel_id == parcel_id)
  if complex_id is not None:
    statement = statement.where(Complex.id == complex_id)
  return list(session.scalars(statement).all())


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


def number_between(value: float | int | None, minimum: Any, maximum: Any) -> bool:
  if value is None:
    return True
  min_number = optional_float(minimum)
  max_number = optional_float(maximum)
  return (min_number is None or value >= min_number) and (max_number is None or value <= max_number)


def optional_float(value: Any) -> float | None:
  if value in (None, ""):
    return None
  return float(value)


def age_from_use_date(value: str | None) -> int | None:
  if not value:
    return None
  return 2026 - int(value[:4])


def clamp(value: int, minimum: int, maximum: int) -> int:
  return min(max(value, minimum), maximum)
