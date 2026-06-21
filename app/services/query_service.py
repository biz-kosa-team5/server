from __future__ import annotations

import math
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import repository
from ..dtos.query_dto import QueryRequest
from ..models import Complex, Poi, Region, Trade

DEFAULT_RADIUS_M = 800
DEFAULT_LIMIT = 10
DEFAULT_NEW_BUILD_YEAR = 2020
PYEONG_DIVISOR = 3.3058


def handle_query(session: Session, payload: QueryRequest) -> dict[str, Any]:
  # 이 service는 슬롯을 채우지 않는다. 이미 채워진 JSON을 보고 실행할 조회만 고른다.
  intent = clean_text(payload.intent)

  if intent == "recommendation":
    return recommend_apartments_by_filters(session, payload.slots)

  if intent == "comparison":
    return compare_apartments_by_metrics(session, payload.slots)

  return {
    "success": False,
    "reason": "unsupported_intent",
    "message": "지원하지 않는 질문 유형입니다.",
  }


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
    latest_trade = repository.latest_trade_for_complex(session, complex_row.id)
    if latest_trade_matches(latest_trade, normalized):
      filtered.append(query_result_item(complex_row, latest_trade))

  poi_groups = poi_filter_groups(session, normalized)
  if poi_groups is None:
    return empty_result("recommendation", "poi_not_found", "조건에 맞는 역/교육시설을 찾지 못했습니다.", normalized)

  # 역/학교 조건은 pois 테이블 좌표와 아파트 좌표 사이의 거리로 필터링한다.
  for poi_group in poi_groups:
    filtered = filter_by_poi_distance(filtered, poi_group, radius_m(normalized))

  filtered = sort_query_results(filtered, clean_text(normalized.get("sort_by")))
  limit = repository.clamp(optional_int(normalized.get("limit")) or DEFAULT_LIMIT, 1, 100)
  results = filtered[:limit]

  return {
    "handler": "recommendation",
    "success": bool(results),
    "criteria": criteria_from_slots(normalized),
    "results": results,
    "message": "조건에 맞는 아파트를 조회했습니다." if results else "조건에 맞는 아파트를 찾지 못했습니다.",
  }


def compare_apartments_by_metrics(session: Session, slots: dict[str, Any]) -> dict[str, Any]:
  normalized = normalize_slots(slots)
  names = normalized.get("apartment_names")
  if not isinstance(names, list) or len(names) < 2:
    return empty_result("comparison", "missing_apartment_names", "비교할 아파트명을 2개 이상 입력해야 합니다.", normalized)

  metrics = normalized.get("metrics")
  if not isinstance(metrics, list) or not metrics:
    metrics = [
      "latest_price",
      "pyeong",
      "price_per_pyeong",
      "households",
      "built_year",
      "nearest_station",
      "nearest_school",
    ]

  # 비교는 slots에 들어온 아파트명을 DB에서 찾고, 요청된 metric만 결과에 담는다.
  rows = []
  missing = []
  for name in names:
    complex_row = find_complex_by_name(session, str(name))
    if complex_row is None:
      missing.append(name)
      continue

    latest_trade = repository.latest_trade_for_complex(session, complex_row.id)
    item = comparison_item(complex_row, latest_trade, metrics)
    if "nearest_station" in metrics:
      item["nearestStation"] = nearest_poi_for_complex(session, complex_row, "station")
    if "nearest_school" in metrics:
      item["nearestSchool"] = nearest_poi_for_complex(
        session,
        complex_row,
        "education",
        subtype=clean_text(normalized.get("school_type")),
        name=clean_text(normalized.get("school_name")),
      )
    rows.append(item)

  return {
    "handler": "comparison",
    "success": bool(rows) and not missing,
    "criteria": {
      "apartment_names": names,
      "metrics": metrics,
      "school_type": normalized.get("school_type"),
      "school_name": normalized.get("school_name"),
    },
    "results": rows,
    "missingApartmentNames": missing,
    "message": "아파트 비교 데이터를 조회했습니다." if rows and not missing else "일부 아파트를 찾지 못했습니다.",
  }


def normalize_slots(slots: dict[str, Any]) -> dict[str, Any]:
  # 문자열 "none", "null", ""는 조건 없음으로 보고 None으로 맞춘다.
  normalized: dict[str, Any] = {}
  for key, value in slots.items():
    if isinstance(value, str):
      normalized[key] = clean_text(value)
    elif isinstance(value, list):
      normalized[key] = [clean_text(item) if isinstance(item, str) else item for item in value]
    else:
      normalized[key] = value
  return normalized


def latest_trade_matches(latest_trade: Trade | None, slots: dict[str, Any]) -> bool:
  # 가격/평수 조건은 단지의 최신 거래 한 건을 기준으로 비교한다.
  min_price = optional_int(slots.get("min_price"))
  max_price = optional_int(slots.get("max_price"))
  min_pyeong = repository.optional_float(slots.get("min_pyeong"))

  if latest_trade is None:
    return min_price is None and max_price is None and min_pyeong is None

  if min_price is not None and latest_trade.deal_amount < min_price:
    return False
  if max_price is not None and latest_trade.deal_amount > max_price:
    return False
  if min_pyeong is not None and latest_trade.excl_area / PYEONG_DIVISOR < min_pyeong:
    return False
  return True


def poi_filter_groups(session: Session, slots: dict[str, Any]) -> list[list[Poi]] | None:
  # station_name, school_name, school_type 중 들어온 조건만 pois 조회 조건으로 사용한다.
  groups = []

  station_name = normalize_station_name(clean_text(slots.get("station_name")))
  if station_name is not None:
    station_pois = list(session.scalars(
      select(Poi).where(Poi.category == "station", Poi.name == station_name)
    ).all())
    if not station_pois:
      return None
    groups.append(station_pois)

  school_name = clean_text(slots.get("school_name"))
  school_type = clean_text(slots.get("school_type"))
  if school_name is not None or school_type is not None:
    statement = select(Poi).where(Poi.category == "education")
    if school_name is not None:
      statement = statement.where(Poi.name == school_name)
    if school_type is not None:
      statement = statement.where(Poi.subtype == school_type)
    education_pois = list(session.scalars(statement).all())
    if not education_pois:
      return None
    groups.append(education_pois)

  return groups


def filter_by_poi_distance(items: list[dict[str, Any]], pois: list[Poi], max_distance_m: int) -> list[dict[str, Any]]:
  # 후보 아파트마다 가장 가까운 POI를 찾고, 반경 안에 들어온 아파트만 남긴다.
  filtered = []
  for item in items:
    if item["latitude"] is None or item["longitude"] is None:
      continue
    nearest = nearest_from_pois(item["latitude"], item["longitude"], pois)
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
  return nearest_from_pois(complex_row.latitude, complex_row.longitude, pois)


def nearest_from_pois(latitude: float, longitude: float, pois: list[Poi]) -> dict[str, Any] | None:
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


def find_complex_by_name(session: Session, name: str) -> Complex | None:
  # 먼저 정확히 일치하는 단지를 찾고, 없으면 부분 일치 검색으로 한 번 더 찾는다.
  normalized = clean_text(name)
  if normalized is None:
    return None
  exact = session.scalar(
    select(Complex)
    .where(or_(Complex.name == normalized, Complex.trade_name == normalized))
    .order_by(Complex.id)
    .limit(1)
  )
  if exact is not None:
    return exact
  pattern = f"%{normalized}%"
  return session.scalar(
    select(Complex)
    .where(or_(Complex.name.like(pattern), Complex.trade_name.like(pattern)))
    .order_by(Complex.name)
    .limit(1)
  )


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


def comparison_item(complex_row: Complex, latest_trade: Trade | None, metrics: list[str]) -> dict[str, Any]:
  item = {
    "complexId": complex_row.id,
    "complexName": complex_row.name,
    "parcelId": complex_row.parcel_id,
  }
  if "latest_price" in metrics:
    item["latestDealAmount"] = None if latest_trade is None else latest_trade.deal_amount
  if "pyeong" in metrics:
    item["pyeong"] = None if latest_trade is None else round(latest_trade.excl_area / PYEONG_DIVISOR, 2)
  if "price_per_pyeong" in metrics:
    item["pricePerPyeong"] = (
      None if latest_trade is None else round(latest_trade.deal_amount / (latest_trade.excl_area / PYEONG_DIVISOR), 2)
    )
  if "households" in metrics:
    item["unitCnt"] = complex_row.unit_cnt
  if "built_year" in metrics:
    item["builtYear"] = built_year_from_use_date(complex_row.use_date)
  return item


def sort_query_results(results: list[dict[str, Any]], sort_by: str | None) -> list[dict[str, Any]]:
  if sort_by == "distance_asc":
    return sorted(results, key=lambda item: item.get("distanceM", math.inf))
  if sort_by == "price_asc":
    return sorted(results, key=lambda item: item["latestDealAmount"] if item["latestDealAmount"] is not None else math.inf)
  if sort_by == "price_desc":
    return sorted(results, key=lambda item: item["latestDealAmount"] if item["latestDealAmount"] is not None else -math.inf, reverse=True)
  return results


def calculate_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
  radius = 6371000
  phi1 = math.radians(lat1)
  phi2 = math.radians(lat2)
  delta_phi = math.radians(lat2 - lat1)
  delta_lambda = math.radians(lon2 - lon1)
  haversine = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
  return radius * 2 * math.atan2(math.sqrt(haversine), math.sqrt(1 - haversine))


def criteria_from_slots(slots: dict[str, Any]) -> dict[str, Any]:
  return {
    key: value
    for key, value in slots.items()
    if value not in (None, "", [])
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


def built_year_filter(slots: dict[str, Any]) -> int | None:
  min_built_year = optional_int(slots.get("min_built_year"))
  if min_built_year is not None:
    return min_built_year
  if slots.get("is_new_build") is True:
    return DEFAULT_NEW_BUILD_YEAR
  return None


def built_year_from_use_date(value: str | None) -> int | None:
  if not value:
    return None
  return int(value[:4])


def radius_m(slots: dict[str, Any]) -> int:
  return repository.clamp(optional_int(slots.get("radius_m")) or DEFAULT_RADIUS_M, 1, 10000)


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


def optional_int(value: Any) -> int | None:
  if value in (None, ""):
    return None
  return int(value)
