"""price_trend 정책 정규화 모듈.

LLM이 추출한 슬롯을 DB 조회 가능한 criteria로 변환한다.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import Any

from pydantic import ValidationError

from .dto import (
    ANALYSIS_RANKING,
    ANALYSIS_TIMESERIES,
    RANK_BY_CHANGE_RATE,
    TARGET_REGION,
    TrendCriteria,
    TrendError,
    TrendSlots,
)


BASE_DATE = date(2026, 6, 20)

DEFAULT_PERIOD = "1y"
DEFAULT_INTERVAL = "month"
DEFAULT_LIMIT = 5
MAX_LIMIT = 20

AREA_TOLERANCE = 1.0
PYEONG_TO_M2 = 3.3058
EXCLUSIVE_AREA_RATE = 0.75
PYEONG_AREA_TOLERANCE = 3.0

GANGNAM_3_ALIASES = {"강남3구", "강남삼구"}

PERIOD_PATTERN = re.compile(r"^(?P<amount>[1-9]\d*)(?P<unit>m|y)$")


class PriceTrendPolicy:
    """LLM 슬롯을 DB 조회 가능한 price_trend criteria로 변환한다."""

    def __init__(self, base_date: date = BASE_DATE) -> None:
        self.base_date = base_date

    # 조회 조건 생성
    def build_criteria(self, slots: dict[str, Any]) -> TrendCriteria:
        parsed = self._validate_slots(slots)
        raw_slots = parsed.model_dump(exclude_none=True)

        start_date, end_date = self._normalize_date_range(raw_slots)
        area_criteria = self._normalize_area_criteria(raw_slots)

        target_name = parsed.target_name.strip()
        target_key = "".join(target_name.split())

        criteria: TrendCriteria = {
            "analysis_type": parsed.analysis_type,
            "target_type": parsed.target_type,
            "target_name": parsed.target_name,
            "start_date": start_date,
            "end_date": end_date,
            **area_criteria,
        }

        if parsed.target_type == TARGET_REGION:
            if target_key in GANGNAM_3_ALIASES:
                criteria["region_names"] = ["강남구", "서초구", "송파구"]
            else:
                criteria["region_names"] = [target_name]

        if parsed.original_question:
            criteria["original_question"] = parsed.original_question

        if parsed.analysis_type == ANALYSIS_TIMESERIES:
            criteria["interval"] = parsed.interval or DEFAULT_INTERVAL

        if parsed.analysis_type == ANALYSIS_RANKING:
            criteria["rank_by"] = parsed.rank_by or RANK_BY_CHANGE_RATE
            criteria["direction"] = parsed.direction or "desc"
            criteria["limit"] = self._normalize_limit(parsed.limit)

        return criteria

    # 형식 체크
    def _validate_slots(self, slots: dict[str, Any]) -> TrendSlots:
        try:
            return TrendSlots.model_validate(slots)
        except ValidationError:
            raise TrendError(
                "invalid_request",
                "시세추이 슬롯 형식이 올바르지 않습니다.",
            )

    # ----------------------------
    # 기간 보정
    # ----------------------------
    def _normalize_date_range(self, slots: dict[str, Any]) -> tuple[date, date]:
        start: date | None = slots.get("start_date")
        end: date | None = slots.get("end_date")
        period: str | None = slots.get("period")

        # 1. start_date + end_date가 모두 있으면 명시 날짜를 우선한다.
        if start is not None and end is not None:
            return self._validate_date_range(start, end)

        # 2. start_date + period면 start_date부터 period만큼 조회한다.
        if start is not None and period:
            end = self._end_date_from_start_and_period(start, period)
            return self._validate_date_range(start, end)

        # 3. end_date + period면 end_date 기준으로 period만큼 과거를 조회한다.
        if end is not None and period:
            start = self._start_date_from_end_and_period(end, period)
            return self._validate_date_range(start, end)

        # 4. start_date만 있으면 base_date까지 조회한다.
        if start is not None:
            return self._validate_date_range(start, self.base_date)

        # 5. end_date만 있으면 기본 기간만큼 과거를 조회한다.
        if end is not None:
            start = self._start_date_from_end_and_period(end, DEFAULT_PERIOD)
            return self._validate_date_range(start, end)

        # 6. 날짜가 없으면 period 또는 기본 period를 base_date 기준으로 조회한다.
        return self._date_range_from_period(period or DEFAULT_PERIOD)

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
        matched = PERIOD_PATTERN.match(period)
        if matched is None:
            raise TrendError(
                "invalid_period_condition",
                "지원하지 않는 기간 조건입니다.",
            )

        amount = int(matched.group("amount"))
        unit = matched.group("unit")

        return amount if unit == "m" else amount * 12

    def _validate_date_range(self, start: date, end: date) -> tuple[date, date]:
        if end > self.base_date:
            end = self.base_date

        if start > end:
            raise TrendError(
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
    def _normalize_area_criteria(self, slots: dict[str, Any]) -> TrendCriteria:
        has_area = any(
            slots.get(key) is not None
            for key in ("area", "area_min", "area_max")
        )
        has_pyeong = any(
            slots.get(key) is not None
            for key in ("pyeong", "pyeong_min", "pyeong_max")
        )

        if has_area and has_pyeong:
            raise TrendError(
                "invalid_condition",
                "면적㎡ 조건과 평형 조건은 동시에 사용할 수 없습니다.",
            )

        if has_area:
            return self._area_criteria_from_area(slots)

        if has_pyeong:
            return self._area_criteria_from_pyeong(slots)

        return {}

    # 면적 조건 보정
    def _area_criteria_from_area(self, slots: dict[str, Any]) -> TrendCriteria:
        area = slots.get("area")
        area_min = slots.get("area_min")
        area_max = slots.get("area_max")

        if area is not None:
            center = float(area)
            return {
                "area_min": max(0.0, center - AREA_TOLERANCE),
                "area_max": center + AREA_TOLERANCE,
            }

        if area_min is not None and area_max is not None and float(area_min) > float(area_max):
            raise TrendError(
                "invalid_condition",
                "면적 최소값은 최대값보다 클 수 없습니다.",
            )

        criteria: TrendCriteria = {}

        if area_min is not None:
            criteria["area_min"] = float(area_min)

        if area_max is not None:
            criteria["area_max"] = float(area_max)

        return criteria

    # 평 조건 보정
    def _area_criteria_from_pyeong(self, slots: dict[str, Any]) -> TrendCriteria:
        pyeong = slots.get("pyeong")
        pyeong_min = slots.get("pyeong_min")
        pyeong_max = slots.get("pyeong_max")

        if pyeong is not None:
            center = float(pyeong) * PYEONG_TO_M2 * EXCLUSIVE_AREA_RATE
            return {
                "area_min": max(0.0, center - PYEONG_AREA_TOLERANCE),
                "area_max": center + PYEONG_AREA_TOLERANCE,
            }

        if pyeong_min is not None:
            pyeong_min = float(pyeong_min)

        if pyeong_max is not None:
            pyeong_max = float(pyeong_max)

        if pyeong_min is not None and pyeong_max is not None and pyeong_min > pyeong_max:
            raise TrendError(
                "invalid_condition",
                "평형 최소값은 최대값보다 클 수 없습니다.",
            )

        criteria: TrendCriteria = {}

        if pyeong_min is not None:
            criteria["area_min"] = pyeong_min * PYEONG_TO_M2 * EXCLUSIVE_AREA_RATE

        if pyeong_max is not None:
            criteria["area_max"] = pyeong_max * PYEONG_TO_M2 * EXCLUSIVE_AREA_RATE

        return criteria


    # ----------------------------
    # 랭킹 조건 보정
    # ----------------------------
    def _normalize_limit(self, value: int | None) -> int:
        if value is None:
            return DEFAULT_LIMIT

        if value <= 0:
            raise TrendError(
                "invalid_condition",
                "limit은 1 이상이어야 합니다.",
            )

        return min(value, MAX_LIMIT)
