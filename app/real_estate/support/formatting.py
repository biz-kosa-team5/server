from __future__ import annotations

from typing import Any

from app.models import Complex, Trade


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


def complex_search_result(row: Complex) -> dict[str, Any]:
  return {
    "complexId": row.id,
    "complexName": row.name,
    "parcelId": row.parcel_id,
    "latitude": row.latitude,
    "longitude": row.longitude,
    "address": row.address,
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


def optional_float(value: Any) -> float | None:
  if value in (None, ""):
    return None
  return float(value)


def optional_int(value: Any) -> int | None:
  if value in (None, ""):
    return None
  return int(value)


def clean_text(value: Any) -> str | None:
  if value is None:
    return None
  text = str(value).strip()
  if text == "" or text.lower() in {"none", "null"}:
    return None
  return text


def normalize_slots(slots: dict[str, Any]) -> dict[str, Any]:
  normalized: dict[str, Any] = {}
  for key, value in slots.items():
    if isinstance(value, str):
      normalized[key] = clean_text(value)
    elif isinstance(value, list):
      normalized[key] = [clean_text(item) if isinstance(item, str) else item for item in value]
    else:
      normalized[key] = value
  return normalized


def criteria_from_slots(slots: dict[str, Any]) -> dict[str, Any]:
  return {
    key: value
    for key, value in slots.items()
    if value not in (None, "", []) and not key.startswith("_")
  }


def empty_result(handler: str, reason: str, message: str, slots: dict[str, Any]) -> dict[str, Any]:
  return {
    "handler": handler,
    "success": False,
    "reason": reason,
    "criteria": criteria_from_slots(slots),
    "results": [],
    "message": message,
  }


def clamp(value: int, minimum: int, maximum: int) -> int:
  return min(max(value, minimum), maximum)


def built_year_from_use_date(value: str | None) -> int | None:
  if not value:
    return None
  return int(value[:4])


def age_from_use_date(value: str | None) -> int | None:
  built_year = built_year_from_use_date(value)
  return None if built_year is None else 2026 - built_year
