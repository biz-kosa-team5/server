from __future__ import annotations

import calendar
import re
from datetime import date

from app.chatbot.features.simple_lookup.dto import (
    QUERY_LOCATION,
    QUERY_RECORD_HIGH,
    QUERY_TRADE_HISTORY,
    SUPPORTED_QUERY_TYPES,
    SimpleLookupCriteria,
    SimpleLookupError,
    SimpleLookupSlots,
)


# 팀 합의 기준일: 현재 적재 데이터의 마지막 거래일
BASE_DATE = date(2026, 6, 20)

DEFAULT_TRADE_LIMIT = 5
MAX_TRADE_LIMIT = 20

AREA_TOLERANCE = 1.0
PYEONG_TO_EXCLUSIVE_RATE = 3.3 * 0.75
PYEONG_TOLERANCE = 3.0

PERIOD_PATTERN = re.compile(r"^(?P<amount>[1-9]\d*)(?P<unit>[my])$")

# 슬롯을 정책에 맞게 검증하고 DAO 조회 조건인 Criteria로 변환
def normalize_simple_lookup_policy(slots: SimpleLookupSlots) -> SimpleLookupCriteria:
    query_type = _normalize_query_type(slots.query_type)
    complex_name = _normalize_complex_name(slots.complex_name)
    area_min, area_max = _normalize_area(slots)
    start_date, end_date = _normalize_period(slots)
    limit = _normalize_limit(query_type, slots.limit)

    return SimpleLookupCriteria(
        query_type=query_type,
        complex_name=complex_name,
        area_min=area_min,
        area_max=area_max,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )

# 조회 유형 문자열을 정리하고 지원 가능한 query_type인지 검증
def _normalize_query_type(query_type: str) -> str:
    query_type = query_type.strip()

    if query_type not in SUPPORTED_QUERY_TYPES:
        raise SimpleLookupError(
            "invalid_request",
            "지원하지 않는 조회 유형입니다.",
        )

    return query_type

# 조회 유형 문자열을 정리하고 지원 가능한 query_type인지 검증
def _normalize_complex_name(complex_name: str) -> str:
    complex_name = " ".join(complex_name.split())

    if not complex_name:
        raise SimpleLookupError(
            "invalid_request",
            "단지명이 필요합니다.",
        )

    return complex_name

# 전용면적 또는 평형 입력을 실제 조회용 면적 범위로 변환
def _normalize_area(slots: SimpleLookupSlots) -> tuple[float | None, float | None]:
    if slots.area is not None and slots.pyeong is not None:
        raise SimpleLookupError(
            "invalid_request",
            "전용면적과 평형은 동시에 사용할 수 없습니다.",
        )

    if slots.area is not None:
        if slots.area <= 0:
            raise SimpleLookupError(
                "invalid_request",
                "전용면적은 0보다 커야 합니다.",
            )

        return (
            round(slots.area - AREA_TOLERANCE, 2),
            round(slots.area + AREA_TOLERANCE, 2),
        )

    if slots.pyeong is not None:
        if slots.pyeong <= 0:
            raise SimpleLookupError(
                "invalid_request",
                "평형은 0보다 커야 합니다.",
            )

        estimated_area = slots.pyeong * PYEONG_TO_EXCLUSIVE_RATE
        return (
            round(estimated_area - PYEONG_TOLERANCE, 2),
            round(estimated_area + PYEONG_TOLERANCE, 2),
        )

    return None, None

# period, start_date, end_date 조합을 조회 시작일과 종료일로 정규화
def _normalize_period(slots: SimpleLookupSlots) -> tuple[date | None, date | None]:
    period = slots.period
    start_date = slots.start_date
    end_date = slots.end_date

    if period is None and start_date is None and end_date is None:
        return None, None

    if period is not None:
        _parse_period(period)

    if period is not None and start_date is None and end_date is None:
        return _subtract_period(BASE_DATE, period), BASE_DATE

    if period is None and start_date is not None and end_date is not None:
        if start_date > end_date:
            raise SimpleLookupError(
                "invalid_request",
                "시작일은 종료일보다 늦을 수 없습니다.",
            )
        return start_date, end_date

    if period is None and start_date is not None:
        if start_date > BASE_DATE:
            raise SimpleLookupError(
                "invalid_request",
                "시작일은 기준일보다 늦을 수 없습니다.",
            )
        return start_date, BASE_DATE

    if period is None and end_date is not None:
        return None, end_date

    if period is not None and start_date is not None and end_date is None:
        return start_date, _add_period(start_date, period)

    raise SimpleLookupError(
        "invalid_request",
        "지원하지 않는 기간 조건 조합입니다.",
    )

# period, start_date, end_date 조합을 조회 시작일과 종료일로 정규화
def _normalize_limit(query_type: str, limit: int | None) -> int | None:
    if query_type == QUERY_LOCATION:
        return None

    if query_type == QUERY_TRADE_HISTORY:
        if limit is None:
            return DEFAULT_TRADE_LIMIT
        if limit <= 0:
            raise SimpleLookupError(
                "invalid_request",
                "실거래 내역 조회 limit은 1 이상이어야 합니다.",
            )
        return min(limit, MAX_TRADE_LIMIT)

    if query_type == QUERY_RECORD_HIGH:
        if limit is not None and limit != 1:
            raise SimpleLookupError(
                "invalid_request",
                "최고가 조회는 1건만 지원합니다.",
            )
        return None

    raise SimpleLookupError(
        "invalid_request",
        "지원하지 않는 조회 유형입니다.",
    )

# 기준일에서 period만큼 이전 날짜를 계산
def _subtract_period(base_date: date, period: str) -> date:
    unit, amount = _parse_period(period)
    months = amount if unit == "m" else amount * 12
    return _shift_month(base_date, -months)

# 시작일에서 period만큼 이후 날짜를 계산
def _add_period(start_date: date, period: str) -> date:
    unit, amount = _parse_period(period)
    months = amount if unit == "m" else amount * 12
    return _shift_month(start_date, months)

# period 문자열이 1m, 6m, 1y 형식인지 검증하고 단위와 값을 분리
def _parse_period(period: str) -> tuple[str, int]:
    matched = PERIOD_PATTERN.fullmatch(period)

    if matched is None:
        raise SimpleLookupError(
            "invalid_request",
            "period는 1m, 6m, 1y 형식이어야 합니다.",
        )

    return matched.group("unit"), int(matched.group("amount"))

# 월 단위 날짜 이동을 처리하고 월말 날짜를 보정
def _shift_month(value: date, months: int) -> date:
    total_month = value.year * 12 + value.month - 1 + months
    target_year, zero_based_month = divmod(total_month, 12)
    target_month = zero_based_month + 1
    target_day = min(
        value.day,
        calendar.monthrange(target_year, target_month)[1],
    )
    return date(target_year, target_month, target_day)
