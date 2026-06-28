"""시세추이 슬롯 추출 호환 모듈."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from .dto import (
    ANALYSIS_RANKING,
    ANALYSIS_TIMESERIES,
    RANK_BY_CHANGE_RATE,
    TARGET_COMPLEX,
    TARGET_REGION,
)


START_YEAR_DURATION_PATTERN = re.compile(
    r"(?P<year>\d{4})\s*년\s*(?:부터|이후)\s*"
    r"(?P<amount>[1-9]\d*)\s*(?P<unit>개월|달|년|연)\s*(?:간|동안)?"
)
RELATIVE_PERIOD_PATTERN = re.compile(
    r"(?:최근|지난)\s*(?P<amount>[1-9]\d*)\s*(?P<unit>개월|달|년|연)"
)
REGION_PATTERN = re.compile(r"강남\s*3구|강남삼구|강남3구|강남구|서초구|송파구")
TREND_KEYWORD_PATTERN = re.compile(
    r"시세\s*추이|시세추이|시세\s*흐름|가격\s*추이|가격\s*흐름|가격\s*변화|실거래가\s*추이"
)
RANKING_PATTERN = re.compile(r"많이\s*오른|상승률\s*높은|오른\s*아파트|많이\s*내린|하락률\s*높은|내린\s*아파트")
DESC_RANKING_PATTERN = re.compile(r"많이\s*오른|상승률\s*높은|오른\s*아파트")
ASC_RANKING_PATTERN = re.compile(r"많이\s*내린|하락률\s*높은|내린\s*아파트")
LIMIT_PATTERN = re.compile(r"(?:top\s*)?(?P<limit>[1-9]\d*)\s*(?:곳|개|건)?", re.IGNORECASE)


def extract_price_trend_slots(question: str) -> dict[str, Any]:
    """LLM 슬롯 누락에 대비해 명확한 가격 추이/순위 표현만 보정한다."""

    normalized = question.strip()
    slots: dict[str, Any] = {"original_question": normalized}

    duration_matched = START_YEAR_DURATION_PATTERN.search(normalized)
    if duration_matched is not None:
        start = date(int(duration_matched.group("year")), 1, 1)
        amount = int(duration_matched.group("amount"))
        unit = duration_matched.group("unit")
        end = (
            date(start.year + amount, 1, 1) - timedelta(days=1)
            if unit in {"년", "연"}
            else _add_months(start, amount) - timedelta(days=1)
        )
        slots["start_date"] = start.isoformat()
        slots["end_date"] = end.isoformat()
        return slots

    matched = RELATIVE_PERIOD_PATTERN.search(normalized)
    if matched is not None:
        amount = matched.group("amount")
        unit = matched.group("unit")
        slots["period"] = f"{amount}{'y' if unit in {'년', '연'} else 'm'}"

    slots.update(_extract_interval(normalized))
    slots.update(_extract_ranking_slots(normalized))
    slots.update(_extract_timeseries_slots(normalized, slots))
    return slots


def _add_months(value: date, months: int) -> date:
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    return date(year, month, 1)


def _extract_interval(text: str) -> dict[str, Any]:
    if "월별" in text:
        return {"interval": "month"}
    if "분기별" in text:
        return {"interval": "quarter"}
    if any(keyword in text for keyword in ("연도별", "년도별", "연간")):
        return {"interval": "year"}
    return {}


def _extract_ranking_slots(text: str) -> dict[str, Any]:
    if RANKING_PATTERN.search(text) is None:
        return {}

    region_name = _extract_region_name(text)
    if not region_name:
        return {}

    slots: dict[str, Any] = {
        "analysis_type": ANALYSIS_RANKING,
        "target_type": TARGET_REGION,
        "target_name": region_name,
        "rank_by": RANK_BY_CHANGE_RATE,
    }
    if DESC_RANKING_PATTERN.search(text) is not None:
        slots["direction"] = "desc"
    elif ASC_RANKING_PATTERN.search(text) is not None:
        slots["direction"] = "asc"

    limit = _extract_limit(text)
    if limit is not None:
        slots["limit"] = limit
    return slots


def _extract_timeseries_slots(text: str, current_slots: dict[str, Any]) -> dict[str, Any]:
    if current_slots.get("analysis_type") == ANALYSIS_RANKING:
        return {}
    keyword_match = TREND_KEYWORD_PATTERN.search(text)
    if keyword_match is None:
        return {}

    target_name = _extract_region_name(text)
    target_type = TARGET_REGION if target_name else TARGET_COMPLEX
    if not target_name:
        target_name = _extract_complex_name(text, keyword_match.start())
    if not target_name:
        return {}

    return {
        "analysis_type": ANALYSIS_TIMESERIES,
        "target_type": target_type,
        "target_name": target_name,
    }


def _extract_region_name(text: str) -> str | None:
    match = REGION_PATTERN.search(text)
    if match is None:
        return None
    name = re.sub(r"\s+", "", match.group(0))
    if name == "강남삼구":
        return "강남3구"
    return name


def _extract_complex_name(text: str, keyword_start: int) -> str | None:
    candidate = text[:keyword_start]
    candidate = RELATIVE_PERIOD_PATTERN.sub("", candidate)
    candidate = START_YEAR_DURATION_PATTERN.sub("", candidate)
    candidate = re.sub(r"\d{4}\s*년", "", candidate)
    candidate = re.sub(r"\d+(?:\.\d+)?\s*(?:평|평형|㎡|m2|제곱미터)", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"(월별|분기별|연도별|년도별|연간)", "", candidate)
    candidate = re.sub(r"(아파트|단지)\s*$", "", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip(" ,")
    return candidate or None


def _extract_limit(text: str) -> int | None:
    top_match = re.search(r"top\s*(?P<limit>[1-9]\d*)", text, flags=re.IGNORECASE)
    if top_match is not None:
        return int(top_match.group("limit"))

    for match in LIMIT_PATTERN.finditer(text):
        value = int(match.group("limit"))
        end = match.end()
        next_text = text[end:end + 2]
        if next_text.startswith(("구", "년", "개월", "달", "평")):
            continue
        return value
    return None


__all__ = [
    "extract_price_trend_slots",
]
