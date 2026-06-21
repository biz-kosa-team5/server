from __future__ import annotations

import re
from typing import Any

from .dto import RecommendationSlots


DISTRICTS = ("강남구", "서초구", "송파구")
SCHOOL_TYPES = ("유치원", "초등학교", "중학교", "고등학교", "특수학교")
DEFAULT_RADIUS_M = 800
DEFAULT_NEW_BUILD_YEAR = 2020


def extract_recommendation_slots(question: str) -> dict[str, Any]:
  slots = RecommendationSlots()
  text = question.strip()

  for district in DISTRICTS:
    if district in text:
      slots.district = district
      break

  station_match = re.search(r"([가-힣A-Za-z0-9]+역)\s*근처", text)
  if station_match is not None:
    slots.station_name = station_match.group(1)
    slots.radius_m = DEFAULT_RADIUS_M
    slots.sort_by = "distance_asc"

  for school_type in SCHOOL_TYPES:
    if school_type in text:
      slots.school_type = school_type
      slots.radius_m = slots.radius_m or DEFAULT_RADIUS_M
      break

  price_match = re.search(r"(\d+(?:\.\d+)?)\s*억", text)
  if price_match is not None:
    price = int(float(price_match.group(1)) * 10000)
    if "이상" in text[price_match.end():price_match.end() + 6]:
      slots.min_price = price
    else:
      slots.max_price = price

  households_match = re.search(r"(\d+)\s*세대\s*이상", text)
  if households_match is not None:
    slots.min_households = int(households_match.group(1))

  pyeong_match = re.search(r"(\d+(?:\.\d+)?)\s*평\s*이상", text)
  if pyeong_match is not None:
    slots.min_pyeong = float(pyeong_match.group(1))

  if "신축" in text:
    slots.is_new_build = True
    slots.min_built_year = DEFAULT_NEW_BUILD_YEAR

  if "싼 곳" in text or "저렴" in text:
    slots.sort_by = "price_asc"

  return slots.model_dump(exclude_none=True)

