from __future__ import annotations

import re
from typing import Any

from .dto import (
  QUERY_LOCATION,
  QUERY_TRADE,
)


def extract_simple_lookup_slots(question: str) -> dict[str, Any]:
  text = question.strip()
  slots: dict[str, Any] = {
    "original_question": text,
    "query_type": infer_query_type(text),
  }

  complex_name = extract_complex_name(text)
  if complex_name is not None:
    slots["complex_name"] = complex_name

  pyeong_match = re.search(r"(\d+(?:\.\d+)?)\s*평", text)
  if pyeong_match is not None:
    slots["pyeong"] = float(pyeong_match.group(1))

  area_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:m2|㎡|제곱미터)", text, re.IGNORECASE)
  if area_match is not None:
    slots["area"] = float(area_match.group(1))

  limit_match = re.search(r"(\d+)\s*건", text)
  if limit_match is not None:
    slots["limit"] = int(limit_match.group(1))

  period_match = re.search(r"최근\s*(\d+)\s*(개월|달|년)", text)
  if period_match is not None:
    unit = "y" if period_match.group(2) == "년" else "m"
    slots["period"] = f"{period_match.group(1)}{unit}"

  if "최고가" in text or "가장 비싼" in text or "제일 비싼" in text:
    slots["price_order"] = "highest"
  if "최저가" in text or "가장 싼" in text or "제일 싸" in text:
    slots["price_order"] = "lowest"
  if any(token in text for token in ("가장 오래된", "제일 오래된", "최초", "처음")):
    slots["sort_order"] = "oldest"

  return slots


def infer_query_type(text: str) -> str:
  if any(token in text for token in ("어디", "위치", "주소", "좌표")):
    return QUERY_LOCATION
  return QUERY_TRADE


def extract_complex_name(text: str) -> str | None:
  cleaned = text
  cleaned = re.sub(r"\d+(?:\.\d+)?\s*(?:평|m2|㎡|제곱미터|건)", " ", cleaned, flags=re.IGNORECASE)
  cleaned = re.sub(r"최근\s*\d+\s*(?:개월|달|년)", " ", cleaned)
  cleaned = re.sub(
    r"(어디\s*(?:있어|야)?|위치|주소|좌표|실거래(?:가|내역)?|거래(?:내역)?|최고가|가장\s*비싼|조회|알려줘|보여줘|궁금해|시세|가격|\?)",
    " ",
    cleaned,
  )
  cleaned = re.sub(r"\s+", " ", cleaned).strip()
  return cleaned or None


__all__ = [
  "extract_simple_lookup_slots",
]
