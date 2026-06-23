from __future__ import annotations

from typing import Any

from app.models import Complex, Trade
from app.real_estate.support import clamp, clean_text, optional_float, optional_int


DEFAULT_RADIUS_M = 800
DEFAULT_NEW_BUILD_YEAR = 2020
PYEONG_DIVISOR = 3.3058


def complex_matches_base_filters(complex_row: Complex, slots: dict[str, Any]) -> bool:
  """지역, 세대수, 신축 여부처럼 아파트 자체 정보로 먼저 후보를 거른다."""
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


def latest_trade_matches(latest_trade: Trade | None, slots: dict[str, Any]) -> bool:
  """최신 실거래가가 가격/평형 조건을 만족하는지 확인한다."""
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


def requested_infra(slots: dict[str, Any]) -> set[str]:
  """사용자가 요청한 인프라 선호 조건을 set으로 정리한다."""
  value = slots.get("infra_preferences")
  if isinstance(value, list):
    return {
      cleaned
      for item in value
      if (cleaned := clean_text(item)) is not None
    }
  if isinstance(value, str):
    cleaned = clean_text(value)
    return set() if cleaned is None else {cleaned}
  return set()


def requested_school_types(slots: dict[str, Any]) -> list[str]:
  """초등학교/중학교/고등학교처럼 여러 교육시설 조건을 list로 맞춘다."""
  value = slots.get("school_types")
  if isinstance(value, list):
    return [
      cleaned
      for item in value
      if (cleaned := clean_text(item)) is not None
    ]
  single = clean_text(slots.get("school_type"))
  return [] if single is None else [single]


def built_year_filter(slots: dict[str, Any]) -> int | None:
  """명시적인 준공연도 조건이 없으면 신축 여부를 기본 연도 조건으로 바꾼다."""
  min_built_year = optional_int(slots.get("min_built_year"))
  if min_built_year is not None:
    return min_built_year
  if slots.get("is_new_build") is True:
    return DEFAULT_NEW_BUILD_YEAR
  return None


def radius_m(slots: dict[str, Any]) -> int:
  """POI 반경은 너무 작거나 큰 값이 들어와도 안전한 범위로 제한한다."""
  return clamp(optional_int(slots.get("radius_m")) or DEFAULT_RADIUS_M, 1, 10000)
