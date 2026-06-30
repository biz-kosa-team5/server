from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Complex, Poi


EARTH_RADIUS_M = 6371000
COMPLEX_NAME_SCAN_LIMIT = 20


def complexes_in_bounds(session: Session, bounds: dict[str, float]) -> list[Complex]:
  return list(session.scalars(
    select(Complex)
    .where(Complex.latitude.is_not(None))
    .where(Complex.longitude.is_not(None))
    .where(Complex.latitude.between(bounds["swLat"], bounds["neLat"]))
    .where(Complex.longitude.between(bounds["swLng"], bounds["neLng"]))
    .order_by(Complex.name)
  ).all())


def search_complexes_by_text(session: Session, query: str, limit: int) -> list[Complex]:
  pattern = f"%{query}%"
  direct_matches = list(session.scalars(
    select(Complex)
    .where(or_(Complex.name.like(pattern), Complex.trade_name.like(pattern), Complex.address.like(pattern)))
    .order_by(Complex.name)
    .limit(limit)
  ).all())

  if len(direct_matches) >= limit:
    return direct_matches

  seen_ids = {row.id for row in direct_matches}
  normalized_matches = [
    row
    for row in ranked_complex_name_matches(session, query, limit=limit)
    if row.id not in seen_ids
  ]
  return [*direct_matches, *normalized_matches][:limit]


def complexes_by_region(session: Session, region_id: int, limit: int, offset: int) -> list[Complex]:
  return list(session.scalars(
    select(Complex)
    .where(Complex.region_id == region_id)
    .order_by(Complex.name)
    .limit(limit)
    .offset(offset)
  ).all())


def get_complex(session: Session, complex_id: int) -> Complex | None:
  return session.get(Complex, complex_id)


def get_first_complex_by_parcel(session: Session, parcel_id: int) -> Complex | None:
  return session.scalar(
    select(Complex).where(Complex.parcel_id == parcel_id).order_by(Complex.id).limit(1)
  )


def get_complex_by_parcel_and_id(session: Session, parcel_id: int, complex_id: int) -> Complex | None:
  return session.scalar(
    select(Complex).where(Complex.parcel_id == parcel_id, Complex.id == complex_id)
  )


def complexes_by_parcel(session: Session, parcel_id: int) -> list[Complex]:
  return list(session.scalars(
    select(Complex).where(Complex.parcel_id == parcel_id).order_by(Complex.name)
  ).all())


def all_complexes_ordered(session: Session) -> list[Complex]:
  return list(session.scalars(select(Complex).order_by(Complex.name)).all())


def complexes_near_pois_by_query(
  session: Session,
  pois: list[Poi],
  max_distance_m: int,
  complex_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
  poi_ids = [poi.id for poi in pois]
  if not poi_ids or complex_ids == []:
    return []

  distance_expr = haversine_distance_expr(
    Complex.latitude,
    Complex.longitude,
    Poi.latitude,
    Poi.longitude,
  )
  statement = (
    select(Complex, Poi, distance_expr.label("distance_m"))
    .join(Poi, Poi.id.in_(poi_ids))
    .where(Complex.latitude.is_not(None))
    .where(Complex.longitude.is_not(None))
    .where(distance_expr <= max_distance_m)
    .order_by(distance_expr)
  )
  if complex_ids is not None:
    statement = statement.where(Complex.id.in_(complex_ids))

  nearest_by_complex_id: dict[int, dict[str, Any]] = {}
  for complex_row, poi, distance_m in session.execute(statement).all():
    if complex_row.id in nearest_by_complex_id:
      continue
    nearest_by_complex_id[complex_row.id] = {
      "complex": complex_row,
      "matchedPoi": {
        "id": poi.id,
        "category": poi.category,
        "name": poi.name,
        "subtype": poi.subtype,
        "latitude": poi.latitude,
        "longitude": poi.longitude,
        "distanceM": round(float(distance_m), 2),
      },
    }
  return list(nearest_by_complex_id.values())


def haversine_distance_expr(lat1, lon1, lat2, lon2):
  return EARTH_RADIUS_M * 2 * func.asin(
    func.sqrt(
      func.pow(func.sin(func.radians(lat2 - lat1) / 2), 2)
      + func.cos(func.radians(lat1))
      * func.cos(func.radians(lat2))
      * func.pow(func.sin(func.radians(lon2 - lon1) / 2), 2)
    )
  )


def find_complex_by_name(session: Session, name: str) -> Complex | None:
  for candidate in complex_name_query_candidates(name):
    exact = session.scalar(
      select(Complex)
      .where(or_(Complex.name == candidate, Complex.trade_name == candidate))
      .order_by(Complex.id)
      .limit(1)
    )
    if exact is not None:
      return exact

  for candidate in complex_name_query_candidates(name):
    pattern = f"%{candidate}%"
    partial = session.scalar(
      select(Complex)
      .where(or_(Complex.name.like(pattern), Complex.trade_name.like(pattern)))
      .order_by(Complex.name)
      .limit(1)
    )
    if partial is not None:
      return partial

  matches = ranked_complex_name_matches(session, name, limit=1)
  return matches[0] if matches else None


def ranked_complex_name_matches(session: Session, query: str, limit: int = COMPLEX_NAME_SCAN_LIMIT) -> list[Complex]:
  query_keys = complex_name_query_keys(query)
  if not query_keys:
    return []

  scored: list[tuple[int, int, str, Complex]] = []
  for row in session.scalars(select(Complex).order_by(Complex.name)).all():
    score = complex_name_match_score(query_keys, row)
    if score <= 0:
      continue
    scored.append((score, -(row.unit_cnt or 0), row.name, row))

  scored.sort(key=lambda item: (-item[0], item[1], item[2]))
  return [row for _, _, _, row in scored[:limit]]


def complex_name_match_score(query_keys: list[str], row: Complex) -> int:
  row_keys = [
    key
    for key in [
      normalize_complex_name_key(row.name),
      normalize_complex_name_key(row.trade_name),
    ]
    if key
  ]
  best_score = 0
  for query_key in query_keys:
    for row_key in row_keys:
      if query_key == row_key:
        best_score = max(best_score, 100)
      elif query_key in row_key:
        best_score = max(best_score, 80 + min(19, len(query_key)))
      elif row_key in query_key:
        best_score = max(best_score, 60 + min(19, len(row_key)))
      elif min(len(query_key), len(row_key)) >= 4:
        similarity = SequenceMatcher(None, query_key, row_key).ratio()
        if similarity >= 0.78:
          best_score = max(best_score, 40 + int(similarity * 40))
  return best_score


def complex_name_query_candidates(value: Any) -> list[str]:
  text = clean_complex_name_text(value)
  if not text:
    return []

  without_parentheses = re.sub(r"\([^)]*\)", "", text).strip()
  candidates = [text]
  if without_parentheses and without_parentheses != text:
    candidates.append(without_parentheses)
  if text.endswith("아파트") and len(text) > len("아파트"):
    candidates.append(text.removesuffix("아파트"))
  if without_parentheses.endswith("아파트") and len(without_parentheses) > len("아파트"):
    candidates.append(without_parentheses.removesuffix("아파트"))
  if "펠리스" in text:
    candidates.append(text.replace("펠리스", "팰리스"))
  if "펠리스" in without_parentheses:
    candidates.append(without_parentheses.replace("펠리스", "팰리스"))
  if "레미안" in text:
    candidates.append(text.replace("레미안", "래미안"))
  if "레미안" in without_parentheses:
    candidates.append(without_parentheses.replace("레미안", "래미안"))

  return dedupe_texts(candidates)


def complex_name_query_keys(value: Any) -> list[str]:
  keys = [normalize_complex_name_key(candidate) for candidate in complex_name_query_candidates(value)]
  return [key for key in dedupe_texts(keys) if len(key) >= 2]


def normalize_complex_name_key(value: Any) -> str:
  text = clean_complex_name_text(value)
  if not text:
    return ""
  text = normalize_common_korean_vowel_typos(text)
  text = re.sub(r"[^0-9a-zA-Z가-힣]+", "", text)
  return text.replace("펠리스", "팰리스").replace("레미안", "래미안").lower()


def normalize_common_korean_vowel_typos(value: str) -> str:
  # 단지명 검색에서는 ㅐ/ㅔ 입력 오타가 잦아서 같은 검색 키로 본다.
  result = []
  for char in value:
    code = ord(char)
    if not 0xAC00 <= code <= 0xD7A3:
      result.append(char)
      continue

    offset = code - 0xAC00
    choseong = offset // (21 * 28)
    jungseong = (offset % (21 * 28)) // 28
    jongseong = offset % 28
    if jungseong == 5:  # ㅔ -> ㅐ
      jungseong = 1
    result.append(chr(0xAC00 + ((choseong * 21 + jungseong) * 28) + jongseong))
  return "".join(result)


def clean_complex_name_text(value: Any) -> str:
  if value is None:
    return ""
  text = str(value).strip()
  if text == "" or text.lower() in {"none", "null"}:
    return ""
  return text


def dedupe_texts(values: list[str]) -> list[str]:
  result = []
  seen = set()
  for value in values:
    if not value or value in seen:
      continue
    result.append(value)
    seen.add(value)
  return result
