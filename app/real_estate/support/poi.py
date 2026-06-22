from __future__ import annotations

import math
from typing import Any

from app.models import Complex, Poi


def filter_items_by_poi_distance(items: list[dict[str, Any]], pois: list[Poi], max_distance_m: int) -> list[dict[str, Any]]:
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


def nearest_poi_for_complex(complex_row: Complex, pois: list[Poi]) -> dict[str, Any] | None:
  if complex_row.latitude is None or complex_row.longitude is None:
    return None
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
  station_name = value.strip()
  if not station_name:
    return None
  if not station_name.endswith("역"):
    station_name = f"{station_name}역"

  aliases = {
    "잠실역": "잠실(송파구청)역",
  }
  return aliases.get(station_name, station_name)
