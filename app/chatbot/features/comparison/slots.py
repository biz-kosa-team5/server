from __future__ import annotations

import re
from typing import Any


def extract_compare_slots(question: str) -> dict[str, Any]:
  text = question.strip()
  slots: dict[str, Any] = {
    "apartment_names": extract_apartment_names(text),
  }
  metrics = extract_metrics(text)
  if metrics is not None:
    slots["metrics"] = metrics
  if "초등학교" in text:
    slots["school_type"] = "초등학교"
  return slots


def extract_apartment_names(text: str) -> list[str]:
  match = re.search(r"(.+?)(?:랑|와|하고)\s*(.+)", text)
  if match is None:
    return []
  first = clean_apartment_name(match.group(1))
  second = clean_apartment_name(match.group(2))
  return [name for name in [first, second] if name]


def clean_apartment_name(value: str) -> str:
  text = value.strip()
  text = re.sub(r"(가격|세대수|신축|비교|해줘|알려줘|어디가\s*더|둘\s*중|중|이야|\?)", "", text)
  return text.strip()


def extract_metrics(text: str) -> list[str] | None:
  if "가격" in text:
    return ["latest_price", "pyeong", "price_per_pyeong"]
  if "세대수" in text:
    return ["households"]
  if "신축" in text:
    return ["built_year"]
  return None
