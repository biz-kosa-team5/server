"""시세추이 슬롯을 검증하고 DAO 조회 조건으로 정규화한다."""

from __future__ import annotations

import calendar
import math
import re
from datetime import date, timedelta
from typing import Any

from app.chatbot.features.price_trend.dto import (
    QUERY_COMPLEX_TREND,
    QUERY_PRICE_CHANGE_RANKING,
    QUERY_REGION_TREND,
    SUPPORTED_TREND_QUERY_TYPES,
    TrendCriteria,
    TrendError,
    TrendSlots,
)


DEFAULT_TREND_PERIOD = "3y"
DEFAULT_CHANGE_RANKING_PERIOD = "1y"
DEFAULT_RANKING_LIMIT = 5
MAX_RANKING_LIMIT = 20
MIN_CHANGE_WINDOW_TRADE_COUNT = 2
BASE_DATE = date(2026, 6, 20)

PYEONG_TO_SQM = 3.3058
ASSUMED_EXCLUSIVE_RATE = 0.75
AREA_TOLERANCE_SQM = 1.0
PYEONG_TOLERANCE_SQM = 3.0

PERIOD_PATTERN = re.compile(r"^(?P<amount>[1-9]\d*)(?P<unit>[my])$")
MAX_PERIOD_MONTHS = 180
ALLOWED_INTERVALS = {"month", "quarter", "year"}
ALLOWED_CHANGE_DIRECTIONS = {"up", "down", "absolute"}


def normalize_trend_policy(
    slots: TrendSlots,
    *,
    base_date: date | str = BASE_DATE,
) -> TrendCriteria:
    """슬롯을 하나의 불변 조회 조건으로 만든다."""

    if slots.query_type not in SUPPORTED_TREND_QUERY_TYPES:
        raise TrendError(
            "invalid_request",
            "지원하지 않는 시세추이 조회 유형입니다.",
        )

    normalized_base_date = _parse_base_date(base_date)
    _validate_slots(slots)

    target = _normalize_target(slots)
    area = _normalize_area(slots)
    period = _normalize_period(
        slots,
        base_date=normalized_base_date,
        default_period=(
            DEFAULT_CHANGE_RANKING_PERIOD
            if slots.query_type == QUERY_PRICE_CHANGE_RANKING
            else DEFAULT_TREND_PERIOD
        ),
    )

    values: dict[str, Any] = {
        "query_type": slots.query_type,
        **target,
        **area,
        **period,
    }

    if slots.query_type in {QUERY_COMPLEX_TREND, QUERY_REGION_TREND}:
        values["interval"] = normalize_interval(
            slots.interval,
            start_date=period["start_date"],
            end_date=period["end_date"],
        )
    else:
        values.update(
            _normalize_change_ranking(
                slots,
                start_date=period["start_date"],
                end_date=period["end_date"],
            )
        )

    return TrendCriteria(**values)


def _validate_slots(slots: TrendSlots) -> None:
    """슬롯 조합과 숫자값을 검증한다."""

    for field_name in ("area", "pyeong"):
        value = getattr(slots, field_name)
        if value is not None and (
            isinstance(value, bool)
            or not math.isfinite(value)
            or value <= 0
        ):
            raise TrendError(
                "invalid_request",
                f"{field_name}은 0보다 큰 유한 숫자여야 합니다.",
            )

    if slots.limit is not None and slots.limit <= 0:
        raise TrendError("invalid_request", "조회 개수는 1 이상이어야 합니다.")

    if slots.area is not None and slots.pyeong is not None:
        raise TrendError(
            "invalid_request",
            "전용면적과 평형은 함께 사용할 수 없습니다.",
        )

    if slots.period is not None and (
        slots.start_date is not None or slots.end_date is not None
    ):
        raise TrendError(
            "invalid_request",
            "period는 start_date 또는 end_date와 함께 사용할 수 없습니다.",
        )

    if slots.query_type == QUERY_COMPLEX_TREND:
        _reject_present(
            slots,
            ("region_name", "region_names", "change_direction", "limit"),
        )

        if slots.area is None and slots.pyeong is None:
            raise TrendError(
                "missing_area",
                "특정 단지 시세추이는 전용면적 또는 평형을 지정해야 합니다.",
            )

    elif slots.query_type == QUERY_REGION_TREND:
        _reject_present(
            slots,
            ("complex_name", "change_direction", "limit"),
        )
    elif slots.query_type == QUERY_PRICE_CHANGE_RANKING:
        _reject_present(slots, ("complex_name", "interval"))


def _reject_present(slots: TrendSlots, names: tuple[str, ...]) -> None:
    """허용하지 않는 슬롯이 들어왔는지 확인한다."""

    present = [name for name in names if getattr(slots, name) is not None]
    if present:
        raise TrendError(
            "invalid_request",
            f"현재 조회 유형에서는 사용할 수 없는 슬롯입니다: {', '.join(present)}",
        )


def _normalize_target(slots: TrendSlots) -> dict[str, Any]:
    """단지명 또는 지역명을 Criteria에 들어갈 형태로 정규화한다."""

    complex_name = _clean_name(slots.complex_name)
    region_names = _collect_region_names(slots.region_name, slots.region_names)

    if slots.query_type == QUERY_COMPLEX_TREND:
        if complex_name is None:
            raise TrendError("invalid_request", "단지 시세추이에는 단지명이 필요합니다.")
        if region_names:
            raise TrendError("invalid_request", "단지명과 지역명을 함께 사용할 수 없습니다.")
        return {"complex_name": complex_name}

    if complex_name is not None:
        raise TrendError("invalid_request", "지역 조회에는 단지명을 사용할 수 없습니다.")
    if not region_names:
        raise TrendError("invalid_request", "지역명이 필요합니다.")
    return {"region_names": tuple(region_names)}


def _collect_region_names(
    region_name: str | None,
    region_names: list[str] | None,
) -> list[str]:
    """단일 지역명과 복수 지역명을 하나의 목록으로 정리한다."""

    if region_name is not None and region_names is not None:
        raise TrendError(
            "invalid_request",
            "region_name과 region_names는 함께 사용할 수 없습니다.",
        )

    values = [region_name] if region_name is not None else (region_names or [])
    normalized: list[str] = []

    for value in values:
        name = _clean_name(value)
        if name is None:
            raise TrendError("invalid_request", "빈 지역명을 사용할 수 없습니다.")
        if name not in normalized:
            normalized.append(name)

    return normalized


def _clean_name(value: str | None) -> str | None:
    """이름 슬롯의 앞뒤 공백과 연속 공백을 정리한다."""

    if value is None:
        return None
    normalized = " ".join(value.split())
    return normalized or None


def _normalize_area(slots: TrendSlots) -> dict[str, float]:
    """전용면적 또는 평형을 DAO에서 쓸 면적 범위로 바꾼다."""

    if slots.area is not None:
        return {
            "area_min": round(slots.area - AREA_TOLERANCE_SQM, 2),
            "area_max": round(slots.area + AREA_TOLERANCE_SQM, 2),
        }

    if slots.pyeong is not None:
        estimated = slots.pyeong * PYEONG_TO_SQM * ASSUMED_EXCLUSIVE_RATE
        return {
            "area_min": round(estimated - PYEONG_TOLERANCE_SQM, 2),
            "area_max": round(estimated + PYEONG_TOLERANCE_SQM, 2),
        }

    return {}


def _normalize_period(
    slots: TrendSlots,
    *,
    base_date: date,
    default_period: str,
) -> dict[str, str]:
    """기간 슬롯을 시작일과 종료일로 정규화한다."""

    start = _parse_optional_date("start_date", slots.start_date)
    end = _parse_optional_date("end_date", slots.end_date)

    if start is not None and start > base_date:
        raise TrendError("invalid_request", "조회 시작일이 데이터 기준일보다 미래입니다.")
    if end is not None and end > base_date:
        end = base_date
    if start is not None and end is not None and start > end:
        raise TrendError("invalid_request", "조회 시작일은 종료일보다 늦을 수 없습니다.")

    if slots.period is not None:
        start = subtract_calendar_period(base_date, slots.period)
        end = base_date
    elif start is None and end is None:
        start = subtract_calendar_period(base_date, default_period)
        end = base_date
    elif start is None:
        assert end is not None
        start = subtract_calendar_period(end, default_period)
    elif end is None:
        end = base_date

    assert start is not None and end is not None
    return {"start_date": start.isoformat(), "end_date": end.isoformat()}


def normalize_interval(
    interval: str | None,
    *,
    start_date: str,
    end_date: str,
) -> str:
    """집계 간격을 검증하거나 조회 기간에 맞춰 자동 선택한다."""

    if interval is not None:
        if interval not in ALLOWED_INTERVALS:
            raise TrendError(
                "invalid_request",
                "interval은 month, quarter, year 중 하나여야 합니다.",
            )
        return interval

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    if end <= add_calendar_months(start, 24):
        return "month"
    if end <= add_calendar_months(start, 60):
        return "quarter"
    return "year"


def _normalize_change_ranking(
    slots: TrendSlots,
    *,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """가격 변화율 순위 조건을 정리한다."""

    direction = slots.change_direction or "up"
    if direction not in ALLOWED_CHANGE_DIRECTIONS:
        raise TrendError(
            "invalid_request",
            "change_direction은 up, down, absolute 중 하나여야 합니다.",
        )

    limit = min(slots.limit or DEFAULT_RANKING_LIMIT, MAX_RANKING_LIMIT)

    return {
        "change_direction": direction,
        "limit": limit,
        "min_trade_count": MIN_CHANGE_WINDOW_TRADE_COUNT,
        **build_change_windows(start_date, end_date),
    }


def build_change_windows(start_date: str, end_date: str) -> dict[str, str]:
    """가격 변화율 비교용 시작 구간과 종료 구간을 만든다."""

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    if end <= add_calendar_months(start, 6):
        months = 1
    elif end <= add_calendar_months(start, 18):
        months = 3
    elif end <= add_calendar_months(start, 36):
        months = 6
    else:
        months = 12

    start_window_end = min(add_calendar_months(start, months) - timedelta(days=1), end)
    end_window_start = max(subtract_calendar_months(end, months) + timedelta(days=1), start)

    if start_window_end >= end_window_start:
        raise TrendError(
            "invalid_request",
            "가격 변화율 비교에는 시작 구간과 종료 구간이 겹치지 않는 더 긴 기간이 필요합니다.",
        )

    return {
        "start_window_start": start.isoformat(),
        "start_window_end": start_window_end.isoformat(),
        "end_window_start": end_window_start.isoformat(),
        "end_window_end": end.isoformat(),
    }


def parse_period(period: str) -> int:
    """period 문자열을 개월 수로 변환한다."""

    matched = PERIOD_PATTERN.fullmatch(period)
    if matched is None:
        raise TrendError(
            "invalid_request",
            "period는 양의 정수 뒤에 m 또는 y를 붙여 입력해야 합니다.",
        )

    amount = int(matched.group("amount"))
    months = amount if matched.group("unit") == "m" else amount * 12

    if months > MAX_PERIOD_MONTHS:
        raise TrendError(
            "unsupported_request",
            f"조회 기간은 최대 {MAX_PERIOD_MONTHS}개월까지 지원합니다.",
        )

    return months


def subtract_calendar_period(value: date, period: str) -> date:
    """기준일에서 period만큼 달력 월 기준으로 뺀다."""

    return subtract_calendar_months(value, parse_period(period))


def add_calendar_months(value: date, months: int) -> date:
    """월말을 보정하면서 달력 월을 더한다."""

    total_months = value.year * 12 + value.month - 1 + months
    year, zero_based_month = divmod(total_months, 12)
    month = zero_based_month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def subtract_calendar_months(value: date, months: int) -> date:
    """월말을 보정하면서 달력 월을 뺀다."""

    return add_calendar_months(value, -months)


def _parse_optional_date(field_name: str, value: str | None) -> date | None:
    """선택 날짜 문자열을 date로 변환한다."""

    if value is None:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise TrendError(
            "invalid_request",
            f"{field_name}은 YYYY-MM-DD 형식이어야 합니다.",
        ) from error


def _parse_base_date(value: date | str) -> date:
    """기준일을 date로 변환한다."""

    if isinstance(value, date):
        return value

    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("base_date는 date 또는 YYYY-MM-DD 문자열이어야 합니다.") from error
