from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session

from app.models import Complex, Trade
from app.real_estate.dao import all_complexes_ordered, education_pois, latest_trade_for_complex, station_pois
from app.real_estate.support import (
  clamp,
  clean_text,
  criteria_from_slots,
  empty_result,
  filter_items_by_poi_distance,
  normalize_slots,
  normalize_station_name,
  optional_float,
  optional_int,
)


DEFAULT_RADIUS_M = 800
DEFAULT_LIMIT = 10
DEFAULT_NEW_BUILD_YEAR = 2020
PYEONG_DIVISOR = 3.3058


def recommend_apartments_by_filters(session: Session, slots: dict[str, Any]) -> dict[str, Any]:
  normalized = normalize_slots(slots)
  candidates = [
    complex_row
    for complex_row in all_complexes_ordered(session)
    if complex_matches_base_filters(complex_row, normalized)
  ]

  filtered = []
  for complex_row in candidates:
    latest_trade = latest_trade_for_complex(session, complex_row.id)
    if latest_trade_matches(latest_trade, normalized):
      filtered.append(query_result_item(complex_row, latest_trade))

  poi_groups = find_poi_groups(
    session,
    clean_text(normalized.get("station_name")),
    clean_text(normalized.get("school_name")),
    clean_text(normalized.get("school_type")),
  )
  if poi_groups is None:
    return empty_result("recommendation", "poi_not_found", "조건에 맞는 역/교육시설을 찾지 못했습니다.", normalized)

  for poi_group in poi_groups:
    filtered = filter_items_by_poi_distance(filtered, poi_group, radius_m(normalized))

  filtered = sort_query_results(filtered, clean_text(normalized.get("sort_by")))
  limit = clamp(optional_int(normalized.get("limit")) or DEFAULT_LIMIT, 1, 100)
  results = filtered[:limit]

  return {
    "handler": "recommendation",
    "success": bool(results),
    "criteria": criteria_from_slots(normalized),
    "results": results,
    "message": "조건에 맞는 아파트를 조회했습니다." if results else "조건에 맞는 아파트를 찾지 못했습니다.",
  }


def complex_matches_base_filters(complex_row: Complex, slots: dict[str, Any]) -> bool:
  district = clean_text(slots.get("district"))
  if district is not None and complex_row.region is not None and complex_row.region.name != district:
    return False
  if district is not None and complex_row.region is None:
    return False

  min_households = optional_int(slots.get("min_households"))
  if min_households is not None and (complex_row.unit_cnt is None or complex_row.unit_cnt < min_households):
    return False

  min_built_year = built_year_filter(slots)
  if min_built_year is not None and (complex_row.use_date is None or complex_row.use_date < f"{min_built_year}-01-01"):
    return False
  return True


def find_poi_groups(
  session: Session,
  station_name: str | None,
  school_name: str | None,
  school_type: str | None,
):
  groups = []

  normalized_station_name = normalize_station_name(station_name)
  if normalized_station_name is not None:
    station_matches = station_pois(session, normalized_station_name)
    if not station_matches:
      return None
    groups.append(station_matches)

  if school_name is not None or school_type is not None:
    education_matches = education_pois(session, name=school_name, subtype=school_type)
    if not education_matches:
      return None
    groups.append(education_matches)

  return groups


def latest_trade_matches(latest_trade: Trade | None, slots: dict[str, Any]) -> bool:
  min_price = optional_int(slots.get("min_price"))
  max_price = optional_int(slots.get("max_price"))
  min_pyeong = optional_float(slots.get("min_pyeong"))

  if latest_trade is None:
    return min_price is None and max_price is None and min_pyeong is None

  if min_price is not None and latest_trade.deal_amount < min_price:
    return False
  if max_price is not None and latest_trade.deal_amount > max_price:
    return False
  if min_pyeong is not None and latest_trade.excl_area / PYEONG_DIVISOR < min_pyeong:
    return False
  return True


def query_result_item(complex_row: Complex, latest_trade: Trade | None) -> dict[str, Any]:
  pyeong = None if latest_trade is None else round(latest_trade.excl_area / PYEONG_DIVISOR, 2)
  return {
    "complexId": complex_row.id,
    "complexName": complex_row.name,
    "parcelId": complex_row.parcel_id,
    "address": complex_row.address,
    "latitude": complex_row.latitude,
    "longitude": complex_row.longitude,
    "unitCnt": complex_row.unit_cnt,
    "useDate": complex_row.use_date,
    "latestDealAmount": None if latest_trade is None else latest_trade.deal_amount,
    "latestDealDate": None if latest_trade is None else latest_trade.deal_date,
    "exclArea": None if latest_trade is None else latest_trade.excl_area,
    "pyeong": pyeong,
  }


def sort_query_results(results: list[dict[str, Any]], sort_by: str | None) -> list[dict[str, Any]]:
  if sort_by == "distance_asc":
    return sorted(results, key=lambda item: item.get("distanceM", math.inf))
  if sort_by == "price_asc":
    return sorted(results, key=lambda item: item["latestDealAmount"] if item["latestDealAmount"] is not None else math.inf)
  if sort_by == "price_desc":
    return sorted(results, key=lambda item: item["latestDealAmount"] if item["latestDealAmount"] is not None else -math.inf, reverse=True)
  return results


def built_year_filter(slots: dict[str, Any]) -> int | None:
  min_built_year = optional_int(slots.get("min_built_year"))
  if min_built_year is not None:
    return min_built_year
  if slots.get("is_new_build") is True:
    return DEFAULT_NEW_BUILD_YEAR
  return None


def radius_m(slots: dict[str, Any]) -> int:
  return clamp(optional_int(slots.get("radius_m")) or DEFAULT_RADIUS_M, 1, 10000)
