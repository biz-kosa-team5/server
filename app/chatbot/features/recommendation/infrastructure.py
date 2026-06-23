from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Poi
from app.real_estate.dao import (
  complexes_near_pois_by_query,
  education_pois,
  pois_by_category,
  station_pois,
)
from app.real_estate.support import clean_text, nearest_poi_for_coordinates, normalize_station_name

from .filters import requested_infra, requested_school_types


def find_poi_groups(
  session: Session,
  station_name: str | None,
  school_name: str | None,
  school_type: str | None,
  school_types: list[str],
  infra_preferences: set[str],
) -> list[list[Poi]] | None:
  """역/학교 조건을 실제 POI 목록 묶음으로 변환한다."""
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


def filter_items_by_poi_distance_query(
  session: Session,
  items: list[dict[str, Any]],
  pois: list[Poi],
  max_distance_m: int,
) -> list[dict[str, Any]]:
  """DAO의 거리 쿼리 결과를 추천 item 구조에 맞게 다시 붙인다."""
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


def enrich_infrastructure(session: Session, item: dict[str, Any], slots: dict[str, Any]) -> dict[str, Any]:
  """추천 결과에 가까운 역/교육시설 정보를 붙여 RAG 답변 근거를 만든다."""
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
  if "commercial" in requested_infra(slots):
    notes.append("상권/생활편의 POI 데이터는 현재 DB에 없어 역과 교육시설 데이터만 근거로 답변합니다.")
  return notes
