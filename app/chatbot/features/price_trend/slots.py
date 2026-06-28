"""시세추이 슬롯 추출 호환 모듈."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any


START_YEAR_DURATION_PATTERN = re.compile(
    r"(?P<year>\d{4})\s*년\s*(?:부터|이후)\s*"
    r"(?P<amount>[1-9]\d*)\s*(?P<unit>개월|달|년|연)\s*(?:간|동안)?"
)
RELATIVE_PERIOD_PATTERN = re.compile(
    r"(?:최근|지난)\s*(?P<amount>[1-9]\d*)\s*(?P<unit>개월|달|년|연)"
)


def extract_price_trend_slots(question: str) -> dict[str, Any]:
    """LLM 슬롯 누락에 대비해 안전한 상대 기간 표현만 보정한다."""

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

    return slots


def _add_months(value: date, months: int) -> date:
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    return date(year, month, 1)


__all__ = [
    "extract_price_trend_slots",
]
