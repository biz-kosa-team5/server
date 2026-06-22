from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session

from app.chatbot.service.rag_answer import generate_rag_answer
from app.models import Complex, Poi, Trade
from app.real_estate.dao import (
  all_complexes_ordered,
  complexes_near_pois_by_query,
  education_pois,
  latest_trade_for_complex,
  pois_by_category,
  station_pois,
)
from app.real_estate.support import (
  clamp,
  clean_text,
  criteria_from_slots,
  empty_result,
  nearest_poi_for_coordinates,
  normalize_slots,
  normalize_station_name,
  optional_float,
  optional_int,
)


DEFAULT_RADIUS_M = 800
RECOMMENDATION_RESULT_LIMIT = 5
DEFAULT_NEW_BUILD_YEAR = 2020
PYEONG_DIVISOR = 3.3058


def run_recommendation(session: Session, slots: dict[str, Any], text: str = "") -> dict[str, Any]:
  result = recommend_apartments_by_filters(session, slots)
  result["answer"] = generate_rag_answer(
    question=text,
    intent="recommendation",
    criteria=result.get("criteria", {}),
    results=result.get("results", []),
  )
  return result


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
    requested_school_types(normalized),
    requested_infra(normalized),
  )
  if poi_groups is None:
    return empty_result("recommendation", "poi_not_found", "조건에 맞는 역/교육시설을 찾지 못했습니다.", normalized)

  for poi_group in poi_groups:
    filtered = filter_items_by_poi_distance_query(session, filtered, poi_group, radius_m(normalized))

  enriched = [enrich_infrastructure(session, item, normalized) for item in filtered]
  enriched = sort_query_results(enriched, clean_text(normalized.get("sort_by")))
  requested_limit = optional_int(normalized.get("limit"))
  limit = clamp(requested_limit or RECOMMENDATION_RESULT_LIMIT, 1, RECOMMENDATION_RESULT_LIMIT)
  results = enriched[:limit]

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
  school_types: list[str],
  infra_preferences: set[str],
) -> list[list[Poi]] | None:
  groups: list[list[Poi]] = []

  normalized_station_name = normalize_station_name(station_name)
  if normalized_station_name is not None:
    station_matches = station_pois(session, normalized_station_name)
    if not station_matches:
      return None
    groups.append(station_matches)
  elif "transport" in infra_preferences:
    station_matches = pois_by_category(session, "station")
    if not station_matches:
      return None
    groups.append(station_matches)

  for subtype in school_types:
    education_matches = education_pois(session, name=school_name, subtype=subtype)
    if not education_matches:
      return None
    groups.append(education_matches)

  if not school_types and (school_name is not None or school_type is not None or "education" in infra_preferences):
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


def filter_items_by_poi_distance_query(
  session: Session,
  items: list[dict[str, Any]],
  pois: list[Poi],
  max_distance_m: int,
) -> list[dict[str, Any]]:
  complex_ids = [int(item["complexId"]) for item in items]
  matches = complexes_near_pois_by_query(session, pois, max_distance_m, complex_ids)
  nearest_poi_by_complex_id = {
    match["complex"].id: match["matchedPoi"]
    for match in matches
  }

  filtered = []
  for item in items:
    matched_poi = nearest_poi_by_complex_id.get(item["complexId"])
    if matched_poi is None:
      continue
    copied = dict(item)
    copied.setdefault("matchedPois", []).append(matched_poi)
    distances = [poi["distanceM"] for poi in copied["matchedPois"]]
    copied["distanceM"] = min(distances)
    filtered.append(copied)
  return filtered


def format_deal_amount(value: int | None) -> str:
  if value is None:
    return "정보 없음"
  if value >= 10000:
    return f"{value / 10000:.1f}억 원"
  return f"{value:,}만 원"


def enrich_infrastructure(session: Session, item: dict[str, Any], slots: dict[str, Any]) -> dict[str, Any]:
  enriched = dict(item)
  station = nearest_poi_for_item(session, item, "station")
  education_by_type = nearest_education_by_type(session, item, requested_school_types(slots))
  education = nearest_poi_for_item(
    session,
    item,
    "education",
    subtype=clean_text(slots.get("school_type")),
    name=clean_text(slots.get("school_name")),
  )
  enriched["infrastructure"] = {
    "nearestStation": station,
    "nearestEducation": education,
    "nearestEducationByType": education_by_type,
    "educationDistanceTotalM": education_distance_total(education_by_type),
    "requestedPreferences": sorted(requested_infra(slots)),
    "notes": infrastructure_notes(slots),
  }
  return enriched


def nearest_poi_for_item(
  session: Session,
  item: dict[str, Any],
  category: str,
  subtype: str | None = None,
  name: str | None = None,
) -> dict[str, Any] | None:
  latitude = item.get("latitude")
  longitude = item.get("longitude")
  if latitude is None or longitude is None:
    return None
  return nearest_poi_for_coordinates(
    float(latitude),
    float(longitude),
    pois_by_category(session, category, subtype=subtype, name=name),
  )


def requested_infra(slots: dict[str, Any]) -> set[str]:
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
  value = slots.get("school_types")
  if isinstance(value, list):
    return [
      cleaned
      for item in value
      if (cleaned := clean_text(item)) is not None
    ]
  single = clean_text(slots.get("school_type"))
  return [] if single is None else [single]


def nearest_education_by_type(
  session: Session,
  item: dict[str, Any],
  school_types: list[str],
) -> dict[str, Any]:
  return {
    school_type: nearest_poi_for_item(session, item, "education", subtype=school_type)
    for school_type in school_types
  }


def education_distance_total(education_by_type: dict[str, Any]) -> float | None:
  if not education_by_type:
    return None
  distances = []
  for value in education_by_type.values():
    if not isinstance(value, dict) or value.get("distanceM") is None:
      return None
    distances.append(float(value["distanceM"]))
  return round(sum(distances), 2)


def infrastructure_notes(slots: dict[str, Any]) -> list[str]:
  notes = []
  preferences = requested_infra(slots)
  if "commercial" in preferences:
    notes.append("상권/생활편의 POI 데이터는 현재 DB에 없어 역/교육시설 데이터만 근거로 답변합니다.")
  return notes


def sort_query_results(results: list[dict[str, Any]], sort_by: str | None) -> list[dict[str, Any]]:
  if sort_by == "school_distance_asc":
    return sorted(results, key=school_distance_sort_key)
  if sort_by == "distance_asc":
    return sorted(results, key=distance_sort_key)
  if sort_by == "price_asc":
    return sorted(results, key=lambda item: item["latestDealAmount"] if item["latestDealAmount"] is not None else math.inf)
  if sort_by == "price_desc":
    return sorted(results, key=lambda item: item["latestDealAmount"] if item["latestDealAmount"] is not None else -math.inf, reverse=True)
  return results


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


def built_year_filter(slots: dict[str, Any]) -> int | None:
  min_built_year = optional_int(slots.get("min_built_year"))
  if min_built_year is not None:
    return min_built_year
  if slots.get("is_new_build") is True:
    return DEFAULT_NEW_BUILD_YEAR
  return None


def radius_m(slots: dict[str, Any]) -> int:
  return clamp(optional_int(slots.get("radius_m")) or DEFAULT_RADIUS_M, 1, 10000)
