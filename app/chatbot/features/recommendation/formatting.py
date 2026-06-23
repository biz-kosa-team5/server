from __future__ import annotations

import math
from typing import Any

from app.models import Complex, Trade

from .filters import PYEONG_DIVISOR


RECOMMENDATION_RESULT_LIMIT = 5


def query_result_item(complex_row: Complex, latest_trade: Trade | None) -> dict[str, Any]:
  """DB row를 챗봇 응답에서 쓰기 쉬운 dict 형태로 바꾼다."""
  pyeong = None if latest_trade is None else round(latest_trade.excl_area / PYEONG_DIVISOR, 2)
  latest_deal_amount = None if latest_trade is None else latest_trade.deal_amount
  return {
    "complexId": complex_row.id,
    "complexName": complex_row.name,
    "parcelId": complex_row.parcel_id,
    "address": complex_row.address,
    "latitude": complex_row.latitude,
    "longitude": complex_row.longitude,
    "unitCnt": complex_row.unit_cnt,
    "useDate": complex_row.use_date,
    "latestDealAmount": latest_deal_amount,
    "latestDealAmountText": format_deal_amount(latest_deal_amount),
    "latestDealDate": None if latest_trade is None else latest_trade.deal_date,
    "exclArea": None if latest_trade is None else latest_trade.excl_area,
    "pyeong": pyeong,
  }


def sort_query_results(results: list[dict[str, Any]], sort_by: str | None) -> list[dict[str, Any]]:
  """사용자가 요청한 정렬 기준에 맞춰 추천 후보를 정렬한다."""
  if sort_by == "school_distance_asc":
    return sorted(results, key=school_distance_sort_key)
  if sort_by == "distance_asc":
    return sorted(results, key=distance_sort_key)
  if sort_by == "price_asc":
    return sorted(results, key=lambda item: item["latestDealAmount"] if item["latestDealAmount"] is not None else math.inf)
  if sort_by == "price_desc":
    return sorted(results, key=lambda item: item["latestDealAmount"] if item["latestDealAmount"] is not None else -math.inf, reverse=True)
  return results


def format_deal_amount(value: int | None) -> str:
  """DB의 만원 단위 금액을 사람이 읽는 문자열로 바꾼다."""
  if value is None:
    return "정보 없음"
  if value >= 10000:
    return f"{value / 10000:.1f}억원"
  return f"{value:,}만원"


def school_distance_sort_key(item: dict[str, Any]) -> float:
  total = item.get("infrastructure", {}).get("educationDistanceTotalM")
  return math.inf if total is None else float(total)


def distance_sort_key(item: dict[str, Any]) -> float:
  if item.get("distanceM") is not None:
    return float(item["distanceM"])
  station = item.get("infrastructure", {}).get("nearestStation")
  if isinstance(station, dict) and station.get("distanceM") is not None:
    return float(station["distanceM"])
  return math.inf
