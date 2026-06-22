from __future__ import annotations

import re
from typing import Any

from .dto import (
  PriceChangeRankingItem,
  PriceRankingItem,
  TrendPoint,
  TrendQueryType,
  TrendResult,
  TrendSlots,
)


DEFAULT_REGION_NAMES = ["강남구", "서초구", "송파구"]


def extract_price_trend_slots(question: str) -> dict[str, Any]:
  text = question.strip()
  query_type = infer_query_type(text)
  slots: dict[str, Any] = {
    "original_question": text,
    "query_type": query_type,
  }

  if query_type == TrendQueryType.COMPLEX_TREND.value:
    complex_name = extract_complex_name(text)
    if complex_name is not None:
      slots["complex_name"] = complex_name
  else:
    region_names = extract_region_names(text)
    if len(region_names) == 1:
      slots["region_name"] = region_names[0]
    else:
      slots["region_names"] = region_names

  if query_type == TrendQueryType.PRICE_CHANGE_RANKING.value:
    slots["change_direction"] = "down" if any(token in text for token in ("하락", "내린", "떨어진")) else "up"

  if query_type == TrendQueryType.PRICE_RANKING.value:
    slots["rank_order"] = "lowest" if any(token in text for token in ("최저", "싼", "저렴")) else "highest"

  pyeong_match = re.search(r"(\d+(?:\.\d+)?)\s*평", text)
  if pyeong_match is not None:
    slots["pyeong"] = float(pyeong_match.group(1))

  period_match = re.search(r"최근\s*(\d+)\s*(개월|달|년)", text)
  if period_match is not None:
    unit = "y" if period_match.group(2) == "년" else "m"
    slots["period"] = f"{period_match.group(1)}{unit}"

  limit_match = re.search(r"(\d+)\s*(?:개|곳|위)", text)
  if limit_match is not None:
    slots["limit"] = int(limit_match.group(1))

  return slots


def infer_query_type(text: str) -> str:
  if any(token in text for token in ("많이 오른", "상승", "오른", "하락", "내린", "떨어진")):
    return TrendQueryType.PRICE_CHANGE_RANKING.value
  if any(token in text for token in ("최고가", "최저가", "비싼", "저렴", "싼 곳")):
    return TrendQueryType.PRICE_RANKING.value
  if any(region in text for region in DEFAULT_REGION_NAMES) or "강남 3구" in text:
    return TrendQueryType.REGION_TREND.value
  return TrendQueryType.COMPLEX_TREND.value


def extract_region_names(text: str) -> list[str]:
  if "강남 3구" in text or "강남3구" in text:
    return DEFAULT_REGION_NAMES
  regions = [region for region in DEFAULT_REGION_NAMES if region in text]
  return regions or DEFAULT_REGION_NAMES


def extract_complex_name(text: str) -> str | None:
  cleaned = text
  cleaned = re.sub(r"\d+(?:\.\d+)?\s*(?:평|개|곳|위)", " ", cleaned)
  cleaned = re.sub(r"최근\s*\d+\s*(?:개월|달|년)", " ", cleaned)
  cleaned = re.sub(
    r"(시세\s*추이|시세|추이|가격|얼마|변화|흐름|거래|알려줘|보여줘|궁금해|\?)",
    " ",
    cleaned,
  )
  cleaned = re.sub(r"\s+", " ", cleaned).strip()
  return cleaned or None


__all__ = [
  "PriceChangeRankingItem",
  "PriceRankingItem",
  "TrendPoint",
  "TrendQueryType",
  "TrendResult",
  "TrendSlots",
  "extract_price_trend_slots",
]
