from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import Any

from app.chatbot.features.price_trend.dto import (
    ANALYSIS_RANKING,
    ANALYSIS_TIMESERIES,
    RANK_BY_CHANGE_RATE,
    RANK_BY_MIN_DEAL_AMOUNT,
    SUPPORTED_RANK_BY,
    TARGET_REGION,
    TrendAnalysisSpec,
    TrendError,
    TrendSlots,
)


BASE_DATE = date(2026, 6, 20)
DEFAULT_PERIOD = "1y"
DEFAULT_LIMIT = 5
MAX_LIMIT = 20
MIN_CHANGE_TRADE_COUNT = 2

PYEONG_TO_SQM = 3.3058
ASSUMED_EXCLUSIVE_RATE = 0.75
AREA_TOLERANCE = 1.0
PYEONG_TOLERANCE = 3.0

PERIOD_PATTERN = re.compile(r"^(?P<amount>[1-9]\d*)(?P<unit>[my])$")


def normalize_trend_policy(slots: TrendSlots, *, base_date: date | str = BASE_DATE) -> TrendAnalysisSpec:
    base = _date(base_date)
    _validate(slots)

    start_date, end_date = _period_range(slots, base)
    values: dict[str, Any] = {
        "analysis_type": slots.analysis_type,
        "target_type": slots.target_type,
        "target_name": _clean_name(slots.target_name),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        **_area_range(slots),
    }

    if slots.analysis_type == ANALYSIS_TIMESERIES:
        values["interval"] = _interval(slots.interval)
    else:
        values.update(_ranking_values(slots, start_date, end_date))

    return TrendAnalysisSpec(**values)


def _validate(slots: TrendSlots) -> None:
    if slots.analysis_type == ANALYSIS_RANKING and slots.target_type != TARGET_REGION:
        raise TrendError("invalid_request", "랭킹 조회는 지역만 지원합니다.")
    if slots.period and (slots.start_date or slots.end_date):
        raise TrendError("invalid_request", "period와 start_date/end_date는 함께 사용할 수 없습니다.")
    if slots.limit is not None and slots.limit <= 0:
        raise TrendError("invalid_request", "조회 개수는 1 이상이어야 합니다.")
    if slots.rank_by is not None and slots.rank_by not in SUPPORTED_RANK_BY:
        raise TrendError("invalid_request", f"지원하지 않는 랭킹 기준입니다: {slots.rank_by}")
    if _area_condition_count(slots) > 1:
        raise TrendError("invalid_request", "면적 조건은 하나만 사용할 수 있습니다.")


def _area_condition_count(slots: TrendSlots) -> int:
    return sum([
        slots.area is not None,
        slots.area_min is not None or slots.area_max is not None,
        slots.pyeong is not None,
        slots.pyeong_min is not None or slots.pyeong_max is not None,
    ])


def _clean_name(value: str) -> str:
    name = " ".join(value.split())
    if not name:
        raise TrendError("invalid_request", "대상명이 필요합니다.")
    return name


def _period_range(slots: TrendSlots, base: date) -> tuple[date, date]:
    start = _optional_date("start_date", slots.start_date)
    end = _optional_date("end_date", slots.end_date)

    if slots.period:
        return _subtract_period(base, slots.period), base
    if start is None and end is None:
        return _subtract_period(base, DEFAULT_PERIOD), base
    if start is None:
        assert end is not None
        return _subtract_period(end, DEFAULT_PERIOD), min(end, base)
    if end is None or end > base:
        end = base
    if start > end:
        raise TrendError("invalid_request", "조회 시작일은 종료일보다 늦을 수 없습니다.")
    return start, end


def _area_range(slots: TrendSlots) -> dict[str, float]:
    if slots.area is not None:
        return _range(slots.area, AREA_TOLERANCE)
    if slots.area_min is not None or slots.area_max is not None:
        return _direct_area_range(slots.area_min, slots.area_max)
    if slots.pyeong is not None:
        return _range(_pyeong_to_area(slots.pyeong), PYEONG_TOLERANCE)
    if slots.pyeong_min is not None or slots.pyeong_max is not None:
        low = _pyeong_to_area(slots.pyeong_min or slots.pyeong_max)
        high = _pyeong_to_area(slots.pyeong_max or slots.pyeong_min)
        return {"area_min": round(low - PYEONG_TOLERANCE, 2), "area_max": round(high + PYEONG_TOLERANCE, 2)}
    return {}


def _direct_area_range(area_min: float | None, area_max: float | None) -> dict[str, float]:
    low = area_min if area_min is not None else area_max
    high = area_max if area_max is not None else area_min
    assert low is not None and high is not None
    if low > high:
        raise TrendError("invalid_request", "면적 범위가 올바르지 않습니다.")
    return {"area_min": round(low, 2), "area_max": round(high, 2)}


def _range(value: float, tolerance: float) -> dict[str, float]:
    return {"area_min": round(value - tolerance, 2), "area_max": round(value + tolerance, 2)}


def _pyeong_to_area(value: float | None) -> float:
    assert value is not None
    return value * PYEONG_TO_SQM * ASSUMED_EXCLUSIVE_RATE


def _interval(value: str | None) -> str:
    if value is None:
        return "month"
    if value not in {"month", "quarter", "year"}:
        raise TrendError("invalid_request", "interval은 month, quarter, year 중 하나여야 합니다.")
    return value


def _ranking_values(slots: TrendSlots, start: date, end: date) -> dict[str, Any]:
    rank_by = slots.rank_by or RANK_BY_CHANGE_RATE
    direction = slots.direction or ("asc" if rank_by == RANK_BY_MIN_DEAL_AMOUNT else "desc")
    if direction not in {"asc", "desc"}:
        raise TrendError("invalid_request", "direction은 asc 또는 desc 중 하나여야 합니다.")

    values: dict[str, Any] = {
        "rank_by": rank_by,
        "direction": direction,
        "limit": min(slots.limit or DEFAULT_LIMIT, MAX_LIMIT),
    }
    if rank_by == RANK_BY_CHANGE_RATE:
        values.update({
            "min_trade_count": MIN_CHANGE_TRADE_COUNT,
            **build_change_windows(start.isoformat(), end.isoformat()),
        })
    return values


def build_change_windows(start_date: str, end_date: str) -> dict[str, str]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    start_end = min(_add_months(start, 3) - timedelta(days=1), end)
    end_start = max(_add_months(end, -3) + timedelta(days=1), start)
    if start_end >= end_start:
        raise TrendError("invalid_request", "변화율 비교에는 더 긴 기간이 필요합니다.")
    return {
        "start_window_start": start.isoformat(),
        "start_window_end": start_end.isoformat(),
        "end_window_start": end_start.isoformat(),
        "end_window_end": end.isoformat(),
    }


def parse_period(period: str) -> int:
    matched = PERIOD_PATTERN.fullmatch(period)
    if matched is None:
        raise TrendError("invalid_request", "period는 1m, 6m, 1y 형식이어야 합니다.")
    return int(matched.group("amount")) * (12 if matched.group("unit") == "y" else 1)


def normalize_interval(interval: str | None, *, start_date: str, end_date: str) -> str:
    return _interval(interval)


def subtract_calendar_period(value: date, period: str) -> date:
    return _subtract_period(value, period)


def add_calendar_months(value: date, months: int) -> date:
    return _add_months(value, months)


def subtract_calendar_months(value: date, months: int) -> date:
    return _add_months(value, -months)


def _subtract_period(value: date, period: str) -> date:
    return _add_months(value, -parse_period(period))


def _add_months(value: date, months: int) -> date:
    total = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(total, 12)
    month = month_index + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _optional_date(name: str, value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise TrendError("invalid_request", f"{name}은 YYYY-MM-DD 형식이어야 합니다.") from error


def _date(value: date | str) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)
