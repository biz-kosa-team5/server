from __future__ import annotations

import logging
import math
from typing import Annotated, Any

from fastapi import Depends
from app.models import Complex, Poi


class PoiDistanceService:
  # 추천/비교에서 함께 쓰는 POI 거리 계산 흐름을 강의식 Service class로 감싼다.
  # DB query가 아니라 좌표와 Poi 목록만으로 계산하는 로직만 담당한다.
  def __init__(self) -> None:
    self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

  def filter_items_by_poi_distance(
    self,
    items: list[dict[str, Any]],
    pois: list[Poi],
    max_distance_m: int,
  ) -> list[dict[str, Any]]:
    # 후보 단지 목록에서 주어진 POI 반경 안에 들어오는 단지만 남긴다.
    return _filter_items_by_poi_distance(items, pois, max_distance_m)

  def nearest_poi_for_complex(self, complex_row: Complex, pois: list[Poi]) -> dict[str, Any] | None:
    # 단지 좌표를 기준으로 가장 가까운 POI를 찾는다.
    return _nearest_poi_for_complex(complex_row, pois)

  def nearest_poi_for_coordinates(self, latitude: float, longitude: float, pois: list[Poi]) -> dict[str, Any] | None:
    # 위도/경도 좌표를 직접 받아 가장 가까운 POI를 찾는다.
    return _nearest_poi_for_coordinates(latitude, longitude, pois)


# FastAPI Depends에서 PoiDistanceService를 주입받을 수 있게 하는 타입 별칭이다.
PoiDistanceServiceDep = Annotated[PoiDistanceService, Depends(PoiDistanceService)]


def filter_items_by_poi_distance(items: list[dict[str, Any]], pois: list[Poi], max_distance_m: int) -> list[dict[str, Any]]:
  # 기존 코드가 함수 형태로 호출하던 API를 유지하기 위한 wrapper다.
  return PoiDistanceService().filter_items_by_poi_distance(items, pois, max_distance_m)


def _filter_items_by_poi_distance(items: list[dict[str, Any]], pois: list[Poi], max_distance_m: int) -> list[dict[str, Any]]:
  filtered = []
  for item in items:
    # 좌표가 없는 단지는 거리 계산 자체가 불가능하므로 제외한다.
    if item["latitude"] is None or item["longitude"] is None:
      continue
    nearest = _nearest_poi_for_coordinates(item["latitude"], item["longitude"], pois)
    if nearest is None or nearest["distanceM"] > max_distance_m:
      continue
    item = dict(item)
    item.setdefault("matchedPois", []).append(nearest)
    distances = [poi["distanceM"] for poi in item["matchedPois"]]
    item["distanceM"] = min(distances)
    filtered.append(item)
  return filtered


def nearest_poi_for_complex(complex_row: Complex, pois: list[Poi]) -> dict[str, Any] | None:
  # 기존 public 함수명 유지용 wrapper다.
  return PoiDistanceService().nearest_poi_for_complex(complex_row, pois)


def _nearest_poi_for_complex(complex_row: Complex, pois: list[Poi]) -> dict[str, Any] | None:
  if complex_row.latitude is None or complex_row.longitude is None:
    return None
  return _nearest_poi_for_coordinates(complex_row.latitude, complex_row.longitude, pois)


def nearest_poi_for_coordinates(latitude: float, longitude: float, pois: list[Poi]) -> dict[str, Any] | None:
  # 기존 public 함수명 유지용 wrapper다.
  return PoiDistanceService().nearest_poi_for_coordinates(latitude, longitude, pois)


def _nearest_poi_for_coordinates(latitude: float, longitude: float, pois: list[Poi]) -> dict[str, Any] | None:
  nearest = None
  for poi in pois:
    # 모든 POI와의 haversine 거리를 계산한 뒤 가장 가까운 한 건만 유지한다.
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
  station_name = value.strip()
  if not station_name:
    return None
  if not station_name.endswith("역"):
    station_name = f"{station_name}역"

  aliases = {
    "잠실역": "잠실(송파구청)역",
  }
  return aliases.get(station_name, station_name)
