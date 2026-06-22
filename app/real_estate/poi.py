from __future__ import annotations

import math
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Complex, Poi


def find_poi_groups(
  session: Session,
  station_name: str | None,
  school_name: str | None,
  school_type: str | None,
) -> list[list[Poi]] | None:
  # station_name, school_name, school_type 중 들어온 조건만 pois 조회 조건으로 사용한다.
  groups = []

  normalized_station_name = normalize_station_name(clean_text(station_name))
  if normalized_station_name is not None:
    station_pois = list(session.scalars(
      select(Poi).where(Poi.category == "station", Poi.name == normalized_station_name)
    ).all())
    if not station_pois:
      return None
    groups.append(station_pois)

  normalized_school_name = clean_text(school_name)
  normalized_school_type = clean_text(school_type)
  if normalized_school_name is not None or normalized_school_type is not None:
    statement = select(Poi).where(Poi.category == "education")
    if normalized_school_name is not None:
      statement = statement.where(Poi.name == normalized_school_name)
    if normalized_school_type is not None:
      statement = statement.where(Poi.subtype == normalized_school_type)
    education_pois = list(session.scalars(statement).all())
    if not education_pois:
      return None
    groups.append(education_pois)

  return groups


def filter_items_by_poi_distance(items: list[dict[str, Any]], pois: list[Poi], max_distance_m: int) -> list[dict[str, Any]]:
  # 후보 아파트마다 가장 가까운 POI를 찾고, 반경 안에 들어온 아파트만 남긴다.
  filtered = []
  for item in items:
    if item["latitude"] is None or item["longitude"] is None:
      continue
    nearest = nearest_poi_for_coordinates(item["latitude"], item["longitude"], pois)
    if nearest is None or nearest["distanceM"] > max_distance_m:
      continue
    item = dict(item)
    item.setdefault("matchedPois", []).append(nearest)
    distances = [poi["distanceM"] for poi in item["matchedPois"]]
    item["distanceM"] = min(distances)
    filtered.append(item)
  return filtered


def nearest_poi_for_complex(
  session: Session,
  complex_row: Complex,
  category: str,
  subtype: str | None = None,
  name: str | None = None,
) -> dict[str, Any] | None:
  # 비교 결과에 넣을 "가장 가까운 역/학교" 한 건을 계산한다.
  if complex_row.latitude is None or complex_row.longitude is None:
    return None
  statement = select(Poi).where(Poi.category == category)
  if subtype is not None:
    statement = statement.where(Poi.subtype == subtype)
  if name is not None:
    statement = statement.where(Poi.name == name)
  pois = list(session.scalars(statement).all())
  return nearest_poi_for_coordinates(complex_row.latitude, complex_row.longitude, pois)


def nearest_poi_for_coordinates(latitude: float, longitude: float, pois: list[Poi]) -> dict[str, Any] | None:
  nearest = None
  for poi in pois:
    distance = round(calculate_distance_m(latitude, longitude, poi.latitude, poi.longitude), 2)
    item = {
      "id": poi.id,
      "category": poi.category,
      "name": poi.name,
      "subtype": poi.subtype,
      "latitude": poi.latitude,
      "longitude": poi.longitude,
      "distanceM": distance,
    }
    if nearest is None or item["distanceM"] < nearest["distanceM"]:
      nearest = item
  return nearest


def calculate_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
  radius = 6371000
  phi1 = math.radians(lat1)
  phi2 = math.radians(lat2)
  delta_phi = math.radians(lat2 - lat1)
  delta_lambda = math.radians(lon2 - lon1)
  haversine = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
  return radius * 2 * math.atan2(math.sqrt(haversine), math.sqrt(1 - haversine))


def normalize_station_name(value: str | None) -> str | None:
  if value is None:
    return None
  return value if value.endswith("역") else f"{value}역"


def clean_text(value: Any) -> str | None:
  if value is None:
    return None
  text = str(value).strip()
  if text == "" or text.lower() in {"none", "null"}:
    return None
  return text

