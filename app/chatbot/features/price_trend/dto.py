"""시세추이와 가격 변화 조회의 입출력 DTO."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


QUERY_COMPLEX_TREND = "complex_trend"
QUERY_REGION_TREND = "region_trend"
QUERY_PRICE_CHANGE_RANKING = "price_change_ranking"

SUPPORTED_TREND_QUERY_TYPES = {
    QUERY_COMPLEX_TREND,
    QUERY_REGION_TREND,
    QUERY_PRICE_CHANGE_RANKING,
}


class TrendError(ValueError):
    """예상 가능한 시세추이 업무 실패."""

    def __init__(
        self,
        reason: str,
        message: str,
        *,
        candidates: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.candidates = candidates or []


class TrendSlots(BaseModel):
    """상위 파이프라인이 전달하는 시세추이 슬롯."""

    model_config = ConfigDict(extra="forbid")

    original_question: str | None = None
    query_type: str

    complex_name: str | None = None
    region_name: str | None = None
    region_names: list[str] | None = None

    area: float | None = None
    pyeong: float | None = None

    period: str | None = None
    start_date: str | None = None
    end_date: str | None = None

    interval: str | None = None
    change_direction: str | None = None
    limit: int | None = None

    @field_validator("query_type")
    @classmethod
    def validate_query_type(cls, value: str) -> str:
        """지원하는 H4 query_type인지 검증한다."""

        normalized = value.strip()
        if normalized not in SUPPORTED_TREND_QUERY_TYPES:
            raise ValueError("지원하지 않는 시세추이 조회 유형입니다.")
        return normalized

    @field_validator("area", "pyeong", "limit", mode="before")
    @classmethod
    def reject_boolean_number(cls, value):
        """숫자 슬롯에 boolean 값이 들어오는 것을 차단한다."""

        if isinstance(value, bool):
            raise ValueError("숫자 슬롯에 boolean 값을 사용할 수 없습니다.")
        return value


class TrendCriteria(BaseModel):
    """Policy가 생성하고 DAO가 소비하는 불변 조회 조건."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_type: str

    complex_name: str | None = None
    region_names: tuple[str, ...] = ()

    area_min: float | None = None
    area_max: float | None = None

    start_date: str
    end_date: str
    interval: str | None = None

    change_direction: str | None = None
    limit: int | None = None
    min_trade_count: int | None = None

    start_window_start: str | None = None
    start_window_end: str | None = None
    end_window_start: str | None = None
    end_window_end: str | None = None


class TrendPoint(BaseModel):
    """단지 또는 지역 시세추이의 한 구간 결과."""

    model_config = ConfigDict(extra="forbid")

    period_start: str
    avg_deal_amount: float
    avg_price_per_sqm: float
    min_deal_amount: int
    max_deal_amount: int
    trade_count: int
    avg_exclusive_area: float

    deal_amount_unit: str = "만원"
    price_per_sqm_unit: str = "만원/㎡"


class PriceChangeRankingItem(BaseModel):
    """지역 내 단지별 가격 변화율 순위 결과."""

    model_config = ConfigDict(extra="forbid")

    rank: int
    complex_id: int
    complex_name: str
    address: str | None = None

    start_avg_price_per_sqm: float
    end_avg_price_per_sqm: float
    change_amount: float
    change_rate: float

    start_trade_count: int
    end_trade_count: int
    avg_exclusive_area: float

    price_per_sqm_unit: str = "만원/㎡"


TrendData = TrendPoint | PriceChangeRankingItem


class TrendResult(BaseModel):
    """H4가 상위 파이프라인에 반환하는 공통 결과."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    query_type: str | None = None
    data: list[TrendData] = Field(default_factory=list)

    criteria: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] | None = None

    reason: str | None = None
    message: str = ""

    candidates: list[dict[str, Any]] = Field(default_factory=list)

    @classmethod
    def ok(
        cls,
        *,
        query_type: str,
        criteria: TrendCriteria | dict[str, Any],
        data: list[TrendData],
        message: str,
        summary: dict[str, Any] | None = None,
    ) -> "TrendResult":
        """성공 응답 DTO를 생성한다."""

        return cls(
            success=True,
            query_type=query_type,
            data=data,
            criteria=_criteria_dict(criteria),
            summary=summary,
            message=message,
        )

    @classmethod
    def fail(
        cls,
        *,
        query_type: str | None,
        reason: str,
        message: str,
        criteria: TrendCriteria | dict[str, Any] | None = None,
        candidates: list[dict[str, Any]] | None = None,
    ) -> "TrendResult":
        """실패 응답 DTO를 생성한다."""

        return cls(
            success=False,
            query_type=query_type,
            criteria=_criteria_dict(criteria),
            reason=reason,
            message=message,
            candidates=candidates or [],
        )


def _criteria_dict(
    criteria: TrendCriteria | dict[str, Any] | None,
) -> dict[str, Any]:
    """Criteria 객체를 응답용 dict로 변환한다."""

    if criteria is None:
        return {}
    if isinstance(criteria, TrendCriteria):
        return criteria.model_dump(mode="json", exclude_none=True)
    return criteria
