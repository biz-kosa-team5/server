from __future__ import annotations

import re
from typing import Any

from .dto import (
    QUERY_COMPLEX_PRICE_RECORD,
    QUERY_LOCATION,
    QUERY_REGION_PRICE_RANKING,
    QUERY_REGION_TRADE_HISTORY,
    QUERY_TRADE_HISTORY,
)


REGION_TARGET_PATTERN = r"강남\s*3구|강남삼구|강남3구|강남구|서초구|송파구|강남|서초|송파|[가-힣]+동"


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
    else:
        target_name = _extract_lookup_target_name(text)
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
    if any(token in text for token in ("어디", "위치", "주소", "좌표")) or _looks_like_find_location_question(text):
        return QUERY_LOCATION

    if _has_price_record_expression(text):
        if _looks_like_region_ranking(text):
            return QUERY_REGION_PRICE_RANKING

        return QUERY_COMPLEX_PRICE_RECORD

    if _looks_like_region_trade_history(text):
        return QUERY_REGION_TRADE_HISTORY

    return QUERY_TRADE_HISTORY

def _extract_location_target_name(text: str) -> str | None:
    matched = re.search(
        r"(?P<target>.+?)\s*(?:어디|위치|주소|좌표|찾아\s*(?:줘|주세요|주라)?)",
        text,
    )
    if matched is None:
        return None

    target = _clean_target_name(matched.group("target"))
    if not target:
        return None

    return target


def _looks_like_find_location_question(text: str) -> bool:
    matched = re.search(r"(?P<target>.+?)\s*찾아\s*(?:줘|주세요|주라)?\??$", text)
    if matched is None:
        return False
    target = _clean_target_name(matched.group("target"))
    if not target:
        return False
    return not _looks_like_region_name(target)


def _extract_lookup_target_name(text: str) -> str | None:
    matched = re.search(
        r"(?P<target>.+?)\s*(?:최신|최근|지난|실거래가?|거래내역|거래\s*내역|가격|시세|얼마|최고가|최저가)",
        text,
    )
    if matched is not None:
        target = _clean_target_name(matched.group("target"))
        if target:
            return target

    trailing_match = re.search(
        r"(?:최근\s*)?(?:실거래가?|거래내역|거래\s*내역|가격|시세)\s+(?P<target>.+?)\s*(?:알려|보여|조회|$)",
        text,
    )
    if trailing_match is not None:
        target = _clean_target_name(trailing_match.group("target"))
        if target:
            return target

    return None


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
    matched = re.search(r"(?P<value>\d+)\s*(?:개(?!월)|건|곳)", text)
    if matched is None:
        return None
    return int(matched.group("value"))


def _has_price_record_expression(text: str) -> bool:
    return _extract_price_order(text) is not None


def _looks_like_region_ranking(text: str) -> bool:
    has_region = re.search(REGION_TARGET_PATTERN, text) is not None
    has_ranking_word = any(
        token in text
        for token in ("TOP", "Top", "top", "순위", "랭킹", "아파트", "단지")
    )

    return has_region and has_ranking_word


def _looks_like_region_trade_history(text: str) -> bool:
    if not any(token in text for token in ("실거래", "실거래가", "거래내역", "거래 내역", "최근 거래")):
        return False
    target = _extract_lookup_target_name(text)
    return _looks_like_region_name(target)


def _looks_like_region_name(value: str | None) -> bool:
    if not value:
        return False
    if "아파트" in value:
        return False
    return re.fullmatch(r"[가-힣]{2,}(?:구|동)", value) is not None or value in {"강남", "서초", "송파"}


def _clean_target_name(value: str) -> str:
    text = value
    text = re.sub(r"(?:최신|최근|지난|요즘|현재|가장)\s*", "", text)
    text = re.sub(r"\d+\s*(?:개월|달|년|개|건|곳)", "", text)
    text = re.sub(r"\d{4}\s*년", "", text)
    text = re.sub(r"\d+(?:\.\d+)?\s*(?:평|평형|㎡|m2|제곱미터)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"전용\s*", "", text)
    text = re.sub(r"\s+(?:아파트|단지)\s*$", "", text)
    text = re.sub(r"(?:그리고|또|랑|와|과|하고)\s*$", "", text)
    text = re.sub(r"(?:에서|부터)$", "", text)
    text = text.strip(" ,")
    text = re.sub(r"\s+", "", text)
    return text.strip()
