from __future__ import annotations

import re
from typing import Any


DISTRICTS = ("강남구", "서초구", "송파구")
SCHOOL_TYPES = ("유치원", "초등학교", "중학교", "고등학교", "특수학교")
DEFAULT_RADIUS_M = 800
DEFAULT_NEW_BUILD_YEAR = 2020

TRANSPORT_KEYWORDS = ("역세권", "지하철", "교통", "역 근처", "역 주변", "역 인근")
EDUCATION_KEYWORDS = ("학군", "학교", "교육", "초등학교", "중학교", "고등학교", "유치원")
COMMERCIAL_KEYWORDS = ("상권", "생활편의", "편의시설", "마트", "병원", "카페", "인프라")


def extract_recommendation_slots(question: str) -> dict[str, Any]:
  slots: dict[str, Any] = {}
  text = question.strip()

  district = extract_district(text)
  if district is not None:
    slots["district"] = district

  station_name = extract_station_name(text)
  if station_name is not None:
    slots["station_name"] = station_name
    slots["radius_m"] = DEFAULT_RADIUS_M
    slots["sort_by"] = "distance_asc"

  school_types = extract_school_types(text)
  if len(school_types) == 1:
    slots["school_type"] = school_types[0]
    slots["radius_m"] = slots.get("radius_m") or DEFAULT_RADIUS_M
  elif school_types:
    slots["school_types"] = school_types
    slots["radius_m"] = slots.get("radius_m") or DEFAULT_RADIUS_M
    slots["sort_by"] = "school_distance_asc"

  radius = extract_radius_m(text)
  if radius is not None:
    slots["radius_m"] = radius
    slots["_explicit_radius_m"] = True

  price_slots = extract_price_slots(text)
  slots.update(price_slots)

  households = extract_min_households(text)
  if households is not None:
    slots["min_households"] = households

  pyeong = extract_min_pyeong(text)
  if pyeong is not None:
    slots["min_pyeong"] = pyeong

  if has_new_build_condition(text):
    slots["is_new_build"] = True
    slots["min_built_year"] = DEFAULT_NEW_BUILD_YEAR

  infra_preferences = extract_infra_preferences(text)
  if infra_preferences:
    slots["infra_preferences"] = infra_preferences
    slots["radius_m"] = slots.get("radius_m") or DEFAULT_RADIUS_M
    if "transport" in infra_preferences:
      slots["sort_by"] = slots.get("sort_by") or "distance_asc"
    if "education" in infra_preferences and is_closest_school_query(text):
      slots["sort_by"] = "school_distance_asc"

  sort_by = extract_sort_by(text)
  if sort_by is not None:
    slots["sort_by"] = sort_by

  limit = extract_limit(text)
  if limit is not None:
    slots["limit"] = limit

  return slots


def extract_district(text: str) -> str | None:
  return next((district for district in DISTRICTS if district in text), None)


def extract_station_name(text: str) -> str | None:
  match = re.search(r"([가-힣A-Za-z0-9]+역)\s*(?:근처|주변|인근|역세권)?", text)
  if match is not None:
    return match.group(1)

  connected_match = re.search(
    r"([가-힣A-Za-z0-9]+?)\s*(?:이랑|랑|와|과)\s*(?:가까운|가까이에|근처|주변|인근)",
    text,
  )
  if connected_match is not None:
    return connected_match.group(1)

  near_match = re.search(r"([가-힣A-Za-z0-9]+)\s*(?:근처|주변|인근)", text)
  return None if near_match is None else near_match.group(1)


def extract_school_types(text: str) -> list[str]:
  school_types = []
  if re.search(r"초\s*[,/·]?\s*중\s*[,/·]?\s*고", text) or "초중고" in text:
    return ["초등학교", "중학교", "고등학교"]
  aliases = {
    "초등": "초등학교",
    "초등학교": "초등학교",
    "중학교": "중학교",
    "고등": "고등학교",
    "고등학교": "고등학교",
    "유치원": "유치원",
    "특수학교": "특수학교",
  }
  for keyword, school_type in aliases.items():
    if keyword in text and school_type not in school_types:
      school_types.append(school_type)
  if any(keyword in text for keyword in ("학교", "학군", "교육")):
    single_letter_aliases = {
      "초": "초등학교",
      "중": "중학교",
      "고": "고등학교",
    }
    for keyword, school_type in single_letter_aliases.items():
      if (
        re.search(rf"(?<![가-힣A-Za-z0-9]){keyword}(?![가-힣A-Za-z0-9])", text)
        and school_type not in school_types
      ):
        school_types.append(school_type)
  return school_types


def extract_radius_m(text: str) -> int | None:
  match = re.search(r"(\d+(?:\.\d+)?)\s*(km|킬로|킬로미터|m|미터)\s*(?:이내|안|내)?", text, re.IGNORECASE)
  if match is None:
    return None
  value = float(match.group(1))
  unit = match.group(2).lower()
  if unit in {"km", "킬로", "킬로미터"}:
    return int(value * 1000)
  return int(value)


def extract_price_slots(text: str) -> dict[str, int]:
  slots: dict[str, int] = {}
  for match in re.finditer(r"(\d+(?:\.\d+)?)\s*억\s*(이하|미만|아래|안|까지|이상|초과|넘는|넘어)?", text):
    price = int(float(match.group(1)) * 10000)
    direction = match.group(2) or ""
    if direction in {"이상", "초과", "넘는", "넘어"}:
      slots["min_price"] = price
    else:
      slots["max_price"] = price
  return slots


def extract_min_households(text: str) -> int | None:
  match = re.search(r"(\d+)\s*(?:세대|가구)\s*이상", text)
  return None if match is None else int(match.group(1))


def extract_min_pyeong(text: str) -> float | None:
  match = re.search(r"(\d+(?:\.\d+)?)\s*(?:평|평형)\s*이상", text)
  return None if match is None else float(match.group(1))


def has_new_build_condition(text: str) -> bool:
  return any(keyword in text for keyword in ("신축", "새 아파트", "준신축", "최근 지은"))


def extract_infra_preferences(text: str) -> list[str]:
  preferences = []
  if any(keyword in text for keyword in TRANSPORT_KEYWORDS):
    preferences.append("transport")
  if any(keyword in text for keyword in EDUCATION_KEYWORDS):
    preferences.append("education")
  if any(keyword in text for keyword in COMMERCIAL_KEYWORDS):
    preferences.append("commercial")
  return preferences


def extract_sort_by(text: str) -> str | None:
  if is_closest_school_query(text):
    return "school_distance_asc"
  if any(keyword in text for keyword in ("비싼", "높은 가격", "가격 높은")):
    return "price_desc"
  if any(keyword in text for keyword in ("가까운", "근처", "거리순")):
    return "distance_asc"
  if any(keyword in text for keyword in ("저렴한", "싼", "낮은 가격", "가격 낮은")):
    return "price_asc"
  return None


def is_closest_school_query(text: str) -> bool:
  return any(keyword in text for keyword in ("가장 가까", "제일 가까", "가까이에", "가까운")) and (
    "학교" in text or "학군" in text or "초" in text or "중" in text or "고" in text
  )


def extract_limit(text: str) -> int | None:
  match = re.search(r"(\d+)\s*(?:개|곳|건)\s*(?:추천|보여|알려)?", text)
  return None if match is None else int(match.group(1))
