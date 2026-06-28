from __future__ import annotations

from typing import Any, Literal, TypeAlias
from datetime import date

from pydantic import BaseModel, ConfigDict, Field


ANALYSIS_TIMESERIES = "timeseries"
ANALYSIS_RANKING = "ranking"

TARGET_COMPLEX = "complex"
TARGET_REGION = "region"

RANK_BY_CHANGE_RATE = "change_rate"


AnalysisType: TypeAlias = Literal["timeseries", "ranking"]
TargetType: TypeAlias = Literal["complex", "region"]
RankBy: TypeAlias = Literal["change_rate"]
Direction: TypeAlias = Literal["asc", "desc"]
Interval: TypeAlias = Literal["month", "quarter", "year"]

TrendCriteria: TypeAlias = dict[str, Any]
TrendSummaryMetrics: TypeAlias = dict[str, Any]
TrendRow: TypeAlias = dict[str, Any]
TrendObservation: TypeAlias = "TrendSuccessObservation | TrendFailObservation"


DEFAULT_TREND_UNITS: dict[str, str] = {
    "deal_amount": "만원",
    "price_per_sqm": "만원/㎡",
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

    analysis_type: AnalysisType
    target_type: TargetType
    target_name: str = Field(min_length=1)

    area: float | None = None
    area_min: float | None = None
    area_max: float | None = None
    pyeong: float | None = None
    pyeong_min: float | None = None
    pyeong_max: float | None = None

    period: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    interval: Interval | None = None

    rank_by: RankBy | None = None
    direction: Direction | None = None
    limit: int | None = None


class TrendSuccessObservation(BaseModel):
    """price_trend tool 성공 시 final answer agent에게 넘기는 DB observation."""

    model_config = ConfigDict(extra="forbid")

    handler: str = "price_trend"
    success: Literal[True] = True
    observation_type: str

    criteria: TrendCriteria
    units: dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_TREND_UNITS))
    summary_metrics: TrendSummaryMetrics = Field(default_factory=dict)

    row_count: int
    rows: list[TrendRow]


class TrendFailObservation(BaseModel):
    """price_trend tool 실패 시 final answer agent에게 넘기는 error observation."""

    model_config = ConfigDict(extra="forbid")

    handler: str = "price_trend"
    success: Literal[False] = False
    observation_type: str | None = None

    reason: str
    error: str

    criteria: TrendCriteria = Field(default_factory=dict)
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    slots: dict[str, Any] | None = None
    rows: list[TrendRow] = Field(default_factory=list)
