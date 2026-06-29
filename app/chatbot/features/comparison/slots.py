from __future__ import annotations

import re
from typing import Any


SCHOOL_TYPES = ("유치원", "초등학교", "중학교", "고등학교", "특수학교")
TRANSPORT_KEYWORDS = ("역세권", "지하철", "교통", "역", "역 접근성")
EDUCATION_KEYWORDS = ("학군", "학교", "교육", "초등학교", "중학교", "고등학교", "유치원")
COMMERCIAL_KEYWORDS = ("상권", "생활편의", "편의시설", "마트", "병원", "카페", "인프라")

DEFAULT_METRICS = [
  "latest_price",
  "pyeong",
  "price_per_pyeong",
  "households",
  "built_year",
  "nearest_station",
  "nearest_school",
]


def extract_compare_slots(question: str) -> dict[str, Any]:
  text = question.strip()
  slots: dict[str, Any] = {
    "apartment_names": extract_apartment_names(text),
  }

  metrics = extract_metrics(text)
  if metrics:
    slots["metrics"] = metrics

  school_type = extract_school_type(text)
  if school_type is not None:
    slots["school_type"] = school_type

  infra_preferences = extract_infra_preferences(text)
  if infra_preferences:
    slots["infra_preferences"] = infra_preferences

  return slots


def extract_apartment_names(text: str) -> list[str]:
  comma_names = split_apartment_names_by_separator(text)
  if len(comma_names) >= 2:
    return comma_names[:3]

  match = re.search(r"(.+?)(?:랑|와|과|하고)\s*(.+)", text)
  if match is None:
    return []
  first = clean_apartment_name(match.group(1))
  second = clean_apartment_name(match.group(2))
  return [name for name in [first, second] if name]


def split_apartment_names_by_separator(text: str) -> list[str]:
  subject = re.split(r"\s*(?:비교|차이|둘 중|어디가)\b", text, maxsplit=1)[0]
  parts = re.split(r"\s*(?:,|，|/| vs | VS |vs|VS)\s*", subject)
  return [
    name
    for name in (clean_apartment_name(part) for part in parts)
    if name
  ]


def clean_apartment_name(value: str) -> str:
  text = value.strip()
  text = re.sub(
    r"(가격|시세|거래가|평당가|세대수|대단지|신축|준공|연식|교통|역세권|역\s*접근성|접근성|학군|학교|교육|초등학교|초등|중학교|중등|고등학교|고등|상권|생활편의|편의시설|인프라|미래\s*가격\s*전망|가격\s*전망|미래|전망|재개발|재건축|정비사업|호재|비교|비교해줘|비교해봐|알려줘|해줘|해봐|줘|이랑|랑|와|과|하고|중\s*어디|중\s*더\s*가까운\s*곳|중|더\s*가까운\s*곳|가까운\s*곳|어디가\s*더\s*좋아|어디가\s*더|어디가|가까운지|가까워|야|\?)",
    "",
    text,
  )
  text = text.strip()
  text = re.sub(r"\s+(이|가|은|는)$", "", text).strip()
  if text.endswith("이") and not text.endswith("자이"):
    return text[:-1].strip()
  return text


def extract_school_type(text: str) -> str | None:
  return next((school_type for school_type in SCHOOL_TYPES if school_type in text), None)


def extract_infra_preferences(text: str) -> list[str]:
  preferences = []
  if any(keyword in text for keyword in TRANSPORT_KEYWORDS):
    preferences.append("transport")
  if any(keyword in text for keyword in EDUCATION_KEYWORDS):
    preferences.append("education")
  if any(keyword in text for keyword in COMMERCIAL_KEYWORDS):
    preferences.append("commercial")
  return preferences


def extract_metrics(text: str) -> list[str]:
  metrics: list[str] = []

  if any(keyword in text for keyword in ("가격", "시세", "거래가", "평당가")):
    metrics.extend(["latest_price", "pyeong", "price_per_pyeong"])
  if any(keyword in text for keyword in ("세대수", "대단지", "규모")):
    metrics.append("households")
  if any(keyword in text for keyword in ("신축", "준공", "연식", "오래된")):
    metrics.append("built_year")
  if any(keyword in text for keyword in TRANSPORT_KEYWORDS):
    metrics.append("nearest_station")
  if any(keyword in text for keyword in EDUCATION_KEYWORDS):
    metrics.append("nearest_school")
  if any(keyword in text for keyword in COMMERCIAL_KEYWORDS):
    metrics.extend(["nearest_station", "nearest_school"])

  return dedupe(metrics) if metrics else DEFAULT_METRICS


def dedupe(values: list[str]) -> list[str]:
  result = []
  seen = set()
  for value in values:
    if value in seen:
      continue
    result.append(value)
    seen.add(value)
  return result
