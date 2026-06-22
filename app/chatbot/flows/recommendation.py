from __future__ import annotations

import math
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Complex, Region, Trade
from ...poi.service import filter_items_by_poi_distance, find_poi_groups
from ...real_estate import clamp, latest_trade_for_complex, optional_float
from .common import clean_text, criteria_from_slots, empty_result, normalize_slots


DEFAULT_RADIUS_M = 800
DEFAULT_LIMIT = 10
DEFAULT_NEW_BUILD_YEAR = 2020
PYEONG_DIVISOR = 3.3058


def recommend_apartments_by_filters(session: Session, slots: dict[str, Any]) -> dict[str, Any]:
  normalized = normalize_slots(slots)
  statement = select(Complex).order_by(Complex.name)

  # 값이 들어온 슬롯만 where 조건으로 붙인다. None인 조건은 무시한다.
  district = normalized.get("district")
  if district is not None:
    statement = statement.join(Region).where(Region.name == district)

  min_households = optional_int(normalized.get("min_households"))
  if min_households is not None:
    statement = statement.where(Complex.unit_cnt.is_not(None), Complex.unit_cnt >= min_households)

  min_built_year = built_year_filter(normalized)
  if min_built_year is not None:
    statement = statement.where(Complex.use_date.is_not(None), Complex.use_date >= f"{min_built_year}-01-01")

  # 단지 기본 조건을 먼저 DB에서 거른 뒤, 최신 거래 조건은 단지별 최신 거래로 검사한다.
  candidates = list(session.scalars(statement).all())
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

  # 역/학교 조건은 pois 테이블 좌표와 아파트 좌표 사이의 거리로 필터링한다.
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


def latest_trade_matches(latest_trade: Trade | None, slots: dict[str, Any]) -> bool:
  # 가격/평수 조건은 단지의 최신 거래 한 건을 기준으로 비교한다.
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


def optional_int(value: Any) -> int | None:
  if value in (None, ""):
    return None
  return int(value)
