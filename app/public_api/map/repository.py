from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Complex, Region, Trade
from ...real_estate import latest_trade_for_complex, optional_float


DEFAULT_BOUNDS = {
  "swLat": 37.40,
  "swLng": 126.90,
  "neLat": 37.60,
  "neLng": 127.20,
}


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


def number_between(value: float | int | None, minimum: Any, maximum: Any) -> bool:
  if value is None:
    return True
  min_number = optional_float(minimum)
  max_number = optional_float(maximum)
  return (min_number is None or value >= min_number) and (max_number is None or value <= max_number)


def age_from_use_date(value: str | None) -> int | None:
  if not value:
    return None
  return 2026 - int(value[:4])
