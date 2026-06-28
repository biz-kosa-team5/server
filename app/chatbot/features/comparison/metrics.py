from __future__ import annotations

from typing import Any

from app.real_estate.support import clean_text


DEFAULT_METRICS = [
  "latest_price",
  "pyeong",
  "price_per_pyeong",
  "households",
  "built_year",
  "nearest_station",
  "nearest_school",
]


def normalize_metrics(metrics: list[str], infra_preferences: set[str]) -> list[str]:
  """요청 metric에 인프라 선호 조건에서 필요한 비교 항목을 추가한다."""
  normalized = list(metrics)
  if "transport" in infra_preferences:
    normalized.append("nearest_station")
  if "education" in infra_preferences:
    normalized.append("nearest_school")
  if "commercial" in infra_preferences:
    normalized.extend(["nearest_station", "nearest_school"])
  return dedupe(normalized)


def requested_infra(slots: dict[str, Any]) -> set[str]:
  """사용자가 요청한 인프라 선호 조건을 set으로 정리한다."""
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


def infrastructure_notes(infra_preferences: set[str]) -> list[str]:
  """현재 DB로 설명할 수 없는 인프라 조건을 사용자에게 알려준다."""
  return []


def dedupe(values: list[str]) -> list[str]:
  result = []
  seen = set()
  for value in values:
    if value in seen:
      continue
    result.append(value)
    seen.add(value)
  return result
