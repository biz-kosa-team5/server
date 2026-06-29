from __future__ import annotations

import re
from typing import Any

from .dto import (
    QUERY_COMPLEX_PRICE_RECORD,
    QUERY_LOCATION,
    QUERY_REGION_PRICE_RANKING,
    QUERY_TRADE_HISTORY,
)


def extract_simple_lookup_slots(question: str) -> dict[str, Any]:
    text = question.strip()
    query_type = infer_query_type(text)
    slots: dict[str, Any] = {
        "original_question": text,
        "query_type": query_type,
    }

    if query_type == QUERY_LOCATION:
        target_name = _extract_location_target_name(text)
        if target_name is not None:
            slots["target_name"] = target_name

    date_range = _extract_year_duration_range(text)
    if date_range is not None:
        start_date, end_date = date_range
        slots["start_date"] = start_date
        slots["end_date"] = end_date
    else:
        period = _extract_period(text)
        if period is not None:
            slots["period"] = period

    period = _extract_period(text)
    if period is not None:
        slots["period"] = period

    area = _extract_area(text)
    if area is not None:
        slots["area"] = area

    pyeong = _extract_pyeong(text)
    if pyeong is not None:
        slots["pyeong"] = pyeong

    price_order = _extract_price_order(text)
    if price_order is not None:
        slots["price_order"] = price_order

    sort_order = _extract_sort_order(text)
    if sort_order is not None:
        slots["sort_order"] = sort_order

    limit = _extract_limit(text)
    if limit is not None:
        slots["limit"] = limit

    return slots


def infer_query_type(text: str) -> str:
    if any(token in text for token in ("어디", "위치", "주소", "좌표")):
        return QUERY_LOCATION

    if _has_price_record_expression(text):
        if _looks_like_region_ranking(text):
            return QUERY_REGION_PRICE_RANKING

        return QUERY_COMPLEX_PRICE_RECORD

    return QUERY_TRADE_HISTORY

def _extract_location_target_name(text: str) -> str | None:
    matched = re.search(
        r"(?P<target>.+?)\s*(?:어디|위치|주소|좌표)",
        text,
    )
    if matched is None:
        return None

    target = matched.group("target").strip()
    if not target:
        return None

    return target

def _extract_year_duration_range(text: str) -> tuple[str, str] | None:
    matched = re.search(
        r"(?P<start_year>(?:19|20)\d{2})\s*년\s*부터\s*(?P<years>\d+)\s*년\s*간",
        text,
    )
    if matched is None:
        return None

    start_year = int(matched.group("start_year"))
    years = int(matched.group("years"))

    end_year = start_year + years - 1

    return (
        f"{start_year}-01-01",
        f"{end_year}-12-31",
    )


def _extract_period(text: str) -> str | None:
    matched = re.search(
        r"(?:최근|지난)\s*(?P<value>\d+)\s*(?P<unit>개월|달|년)",
        text,
    )
    if matched is None:
        return None

    unit = "y" if matched.group("unit") == "년" else "m"
    return f"{matched.group('value')}{unit}"

def _extract_area(text: str) -> float | None:
    matched = re.search(
        r"(?P<value>\d+(?:\.\d+)?)\s*(?:m2|㎡|제곱미터)",
        text,
        re.IGNORECASE,
    )
    if matched is None:
        return None

    return float(matched.group("value"))


def _extract_pyeong(text: str) -> float | None:
    matched = re.search(r"(?P<value>\d+(?:\.\d+)?)\s*(?:평|평형)", text)
    if matched is None:
        return None

    return float(matched.group("value"))


def _extract_price_order(text: str) -> str | None:
    if any(token in text for token in ("최고가", "가장 비싼", "제일 비싼")):
        return "highest"

    if any(token in text for token in ("최저가", "가장 싼", "제일 싼", "제일 싸")):
        return "lowest"

    return None


def _extract_sort_order(text: str) -> str | None:
    if any(token in text for token in ("가장 오래된", "제일 오래된", "최초", "처음")):
        return "oldest"

    return None


def _extract_limit(text: str) -> int | None:
    matched = re.search(r"(?P<value>\d+)\s*건", text)
    if matched is None:
        return None
    return int(matched.group("value"))


def _has_price_record_expression(text: str) -> bool:
    return _extract_price_order(text) is not None


def _looks_like_region_ranking(text: str) -> bool:
    has_region = any(
        region in text
        for region in ("강남구", "서초구", "송파구", "강남", "서초", "송파")
    )
    has_ranking_word = any(
        token in text
        for token in ("TOP", "Top", "top", "순위", "랭킹", "아파트", "단지")
    )

    return has_region and has_ranking_word
