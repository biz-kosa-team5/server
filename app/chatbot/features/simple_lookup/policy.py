"""simple_lookup 정책 정규화 모듈.

검증된 슬롯을 단순조회 정책에 맞는 DB 조회 criteria로 변환한다.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from app.chatbot.features.simple_lookup.dto import (
    PRICE_HIGHEST,
    QUERY_COMPLEX_PRICE_RECORD,
    QUERY_LOCATION,
    QUERY_REGION_PRICE_RANKING,
    QUERY_TRADE_HISTORY,
    SORT_LATEST,
    SimpleLookupCriteria,
    SimpleLookupError,
    SimpleLookupSlots,
)


# 팀 합의 기준일: 현재 적재 데이터의 마지막 거래일
BASE_DATE = date(2026, 6, 20)

DEFAULT_TRADE_HISTORY_LIMIT = 5
DEFAULT_PRICE_RECORD_LIMIT = 1
DEFAULT_REGION_RANKING_LIMIT = 5
MAX_LIMIT = 20

AREA_TOLERANCE = 1.0
PYEONG_TO_M2 = 3.3058
EXCLUSIVE_AREA_RATE = 0.75
PYEONG_AREA_TOLERANCE = 3.0


class SimpleLookupPolicy:
    """검증된 단순조회 슬롯을 DB 조회 가능한 criteria로 변환한다."""

    def __init__(self, base_date: date = BASE_DATE) -> None:
        self.base_date = base_date

    # 조회 조건 생성
    def build_criteria(self, slots: SimpleLookupSlots) -> SimpleLookupCriteria:
        target_name = self._normalize_target_name(slots.target_name)
        self._reject_unsupported_question(slots.original_question)

        # 위치 조회는 단지 대상만 필요하다.
        # 면적/기간/정렬/limit 조건은 위치 조회에 의미가 없으므로 무시한다.
        if slots.query_type == QUERY_LOCATION:
            return SimpleLookupCriteria(
                query_type=slots.query_type,
                target_name=target_name,
            )

        start_date, end_date = self._normalize_date_range(slots)
        area_criteria = self._normalize_area_criteria(slots)

        return SimpleLookupCriteria(
            query_type=slots.query_type,
            target_name=target_name,
            start_date=start_date,
            end_date=end_date,
            limit=self._normalize_limit(
                query_type=slots.query_type,
                value=slots.limit,
            ),
            sort_order=self._normalize_sort_order(
                query_type=slots.query_type,
                value=slots.sort_order,
            ),
            price_order=self._normalize_price_order(
                query_type=slots.query_type,
                value=slots.price_order,
            ),
            **area_criteria,
        )

    # ----------------------------
    # 대상명 보정
    # ----------------------------
    def _normalize_target_name(self, target_name: str) -> str:
        normalized = "".join(target_name.split())

        if not normalized:
            raise SimpleLookupError(
                "invalid_request",
                "조회 대상명이 필요합니다.",
            )

        return normalized

    def _reject_unsupported_question(self, original_question: str | None) -> None:
        if original_question is None:
            return

        if "신고가" in original_question or "신저가" in original_question:
            raise SimpleLookupError(
                "unsupported_query",
                "신고가/신저가 갱신 여부는 단순 조회에서 처리하지 않습니다.",
            )

    # ----------------------------
    # 기간 보정
    # ----------------------------
    def _normalize_date_range(
        self,
        slots: SimpleLookupSlots,
    ) -> tuple[date | None, date | None]:
        start: date | None = slots.start_date
        end: date | None = slots.end_date
        period: str | None = slots.period

        # 1. 기간 조건이 없으면 전체 기간에서 조회한다.
        if start is None and end is None and period is None:
            return None, None

        # 2. start_date + end_date가 모두 있으면 명시 날짜를 우선한다.
        if start is not None and end is not None:
            return self._validate_date_range(start, end)

        # 3. start_date + period면 start_date부터 period만큼 조회한다.
        if start is not None and period:
            end = self._end_date_from_start_and_period(start, period)
            return self._validate_date_range(start, end)

        # 4. end_date + period면 end_date 기준으로 period만큼 과거를 조회한다.
        if end is not None and period:
            start = self._start_date_from_end_and_period(end, period)
            return self._validate_date_range(start, end)

        # 5. start_date만 있으면 base_date까지 조회한다.
        if start is not None:
            return self._validate_date_range(start, self.base_date)

        # 6. end_date만 있으면 시작일 제한 없이 해당 날짜까지 조회한다.
        if end is not None:
            return None, min(end, self.base_date)

        # 7. period만 있으면 base_date 기준으로 조회한다.
        # 위 분기들을 통과했다면 논리상 period만 남는다.
        return self._date_range_from_period(period)

    def _date_range_from_period(self, period: str) -> tuple[date, date]:
        start = self._start_date_from_end_and_period(self.base_date, period)
        return start, self.base_date

    def _end_date_from_start_and_period(self, start: date, period: str) -> date:
        months = self._period_to_months(period)
        end = self._add_months(start, months) - timedelta(days=1)
        return min(end, self.base_date)

    def _start_date_from_end_and_period(self, end: date, period: str) -> date:
        end = min(end, self.base_date)
        months = self._period_to_months(period)
        return self._add_months(end, -months) + timedelta(days=1)

    def _period_to_months(self, period: str) -> int:
        # period 형식은 DTO에서 이미 검증한다. 예: 3m, 1y
        amount = int(period[:-1])
        unit = period[-1]

        return amount if unit == "m" else amount * 12

    def _validate_date_range(
        self,
        start: date,
        end: date,
    ) -> tuple[date, date]:
        if end > self.base_date:
            end = self.base_date

        if start > end:
            raise SimpleLookupError(
                "invalid_period_condition",
                "조회 시작일은 종료일보다 늦을 수 없습니다.",
            )

        return start, end

    def _add_months(self, value: date, months: int) -> date:
        month_index = value.month - 1 + months
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        day = min(value.day, calendar.monthrange(year, month)[1])

        return date(year, month, day)

    # ----------------------------
    # 면적 보정
    # ----------------------------
    def _normalize_area_criteria(
        self,
        slots: SimpleLookupSlots,
    ) -> dict[str, float]:
        if slots.area is not None and slots.pyeong is not None:
            raise SimpleLookupError(
                "invalid_condition",
                "면적㎡ 조건과 평형 조건은 동시에 사용할 수 없습니다.",
            )

        if slots.area is not None:
            center = float(slots.area)
            return {
                "area_min": max(0.0, center - AREA_TOLERANCE),
                "area_max": center + AREA_TOLERANCE,
            }

        if slots.pyeong is not None:
            center = float(slots.pyeong) * PYEONG_TO_M2 * EXCLUSIVE_AREA_RATE
            return {
                "area_min": max(0.0, center - PYEONG_AREA_TOLERANCE),
                "area_max": center + PYEONG_AREA_TOLERANCE,
            }

        return {}

    # ----------------------------
    # 조회 개수/정렬 조건 보정
    # ----------------------------
    def _normalize_limit(
        self,
        *,
        query_type: str,
        value: int | None,
    ) -> int | None:
        if value is not None:
            return min(value, MAX_LIMIT)

        if query_type == QUERY_TRADE_HISTORY:
            return DEFAULT_TRADE_HISTORY_LIMIT

        if query_type == QUERY_COMPLEX_PRICE_RECORD:
            return DEFAULT_PRICE_RECORD_LIMIT

        if query_type == QUERY_REGION_PRICE_RANKING:
            return DEFAULT_REGION_RANKING_LIMIT

        return None

    def _normalize_sort_order(
        self,
        *,
        query_type: str,
        value: str | None,
    ) -> str | None:
        if query_type in {QUERY_LOCATION, QUERY_REGION_PRICE_RANKING,}:
            return None

        return value or SORT_LATEST

    def _normalize_price_order(
        self,
        *,
        query_type: str,
        value: str | None,
    ) -> str | None:
        if query_type in {
            QUERY_COMPLEX_PRICE_RECORD,
            QUERY_REGION_PRICE_RANKING,
        }:
            return value or PRICE_HIGHEST

        return None