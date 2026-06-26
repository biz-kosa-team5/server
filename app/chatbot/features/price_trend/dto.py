from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ANALYSIS_TIMESERIES = "timeseries"
ANALYSIS_RANKING = "ranking"

TARGET_COMPLEX = "complex"
TARGET_REGION = "region"

RANK_BY_CHANGE_RATE = "change_rate"
RANK_BY_MAX_DEAL_AMOUNT = "max_deal_amount"
RANK_BY_MIN_DEAL_AMOUNT = "min_deal_amount"

SUPPORTED_RANK_BY = {
    RANK_BY_CHANGE_RATE,
    RANK_BY_MAX_DEAL_AMOUNT,
    RANK_BY_MIN_DEAL_AMOUNT,
}


class TrendError(ValueError):
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
    model_config = ConfigDict(extra="forbid")

    original_question: str | None = None
    analysis_type: Literal["timeseries", "ranking"]
    target_type: Literal["complex", "region"]
    target_name: str = Field(min_length=1)

    area: float | None = None
    area_min: float | None = None
    area_max: float | None = None
    pyeong: float | None = None
    pyeong_min: float | None = None
    pyeong_max: float | None = None

    period: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    interval: str | None = None

    rank_by: str | None = None
    direction: str | None = None
    limit: int | None = None


class TrendAnalysisSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    analysis_type: Literal["timeseries", "ranking"]
    target_type: Literal["complex", "region"]
    target_name: str

    start_date: str
    end_date: str
    interval: str | None = None

    area_min: float | None = None
    area_max: float | None = None

    rank_by: str | None = None
    direction: str | None = None
    limit: int | None = None

    min_trade_count: int | None = None
    start_window_start: str | None = None
    start_window_end: str | None = None
    end_window_start: str | None = None
    end_window_end: str | None = None

class TrendPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_start: str
    avg_deal_amount: float
    avg_price_per_sqm: float
    trade_count: int


class PriceChangeRankingItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    complex_id: int
    complex_name: str
    address: str | None = None

    max_deal_amount: int | None = None
    min_deal_amount: int | None = None
    start_price_per_sqm: float | None = None
    end_price_per_sqm: float | None = None
    change_amount: float | None = None
    change_rate: float | None = None

    trade_counts: dict[str, int] = Field(default_factory=dict)


TrendData = TrendPoint | PriceChangeRankingItem


class TrendResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool
    analysis_type: str | None = None
    results: list[TrendData] = Field(default_factory=list)
    criteria: dict[str, Any] = Field(default_factory=dict)
    calculation: dict[str, Any] | None = None
    units: dict[str, str] | None = None

    reason: str | None = None
    message: str = ""
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    slots: dict[str, Any] | None = None

    @classmethod
    def ok(
        cls,
        *,
        analysis_type: str,
        criteria: dict[str, Any],
        results: list[TrendData],
        message: str,
        calculation: dict[str, Any] | None = None,
        units: dict[str, str] | None = None,
    ) -> "TrendResult":
        return cls(
            success=True,
            analysis_type=analysis_type,
            criteria=criteria,
            calculation=calculation,
            units=units,
            results=results,
            message=message,
        )

    @classmethod
    def fail(
        cls,
        *,
        analysis_type: str | None,
        reason: str,
        message: str,
        criteria: TrendAnalysisSpec | dict[str, Any] | None = None,
        candidates: list[dict[str, Any]] | None = None,
        slots: dict[str, Any] | None = None,
    ) -> "TrendResult":
        return cls(
            success=False,
            analysis_type=analysis_type,
            criteria=_criteria_dict(criteria),
            reason=reason,
            message=message,
            candidates=candidates or [],
            slots=slots,
        )


def _criteria_dict(criteria: TrendAnalysisSpec | dict[str, Any] | None) -> dict[str, Any]:
    if criteria is None:
        return {}
    if isinstance(criteria, TrendAnalysisSpec):
        return criteria.model_dump(mode="json", exclude_none=True)
    return criteria
