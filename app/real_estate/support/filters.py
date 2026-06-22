from __future__ import annotations

from typing import Any

from app.models import Complex, Trade

from .formatting import age_from_use_date, optional_float


DEFAULT_BOUNDS = {
  "swLat": 37.40,
  "swLng": 126.90,
  "neLat": 37.60,
  "neLng": 127.20,
}


def bounds_from_payload(payload: dict[str, Any]) -> dict[str, float]:
  source = payload.get("bounds") if isinstance(payload.get("bounds"), dict) else payload
  return {
    key: float(source.get(key, fallback))
    for key, fallback in DEFAULT_BOUNDS.items()
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
