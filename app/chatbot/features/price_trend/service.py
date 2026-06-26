from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.chatbot.features.price_trend.dao import PriceTrendDao
from app.chatbot.features.price_trend.dto import (
    ANALYSIS_RANKING,
    ANALYSIS_TIMESERIES,
    PriceChangeRankingItem,
    TrendAnalysisSpec,
    TrendData,
    TrendError,
    TrendPoint,
    TrendResult,
    TrendSlots,
)
from app.chatbot.features.price_trend.policy import normalize_trend_policy


@dataclass(frozen=True)
class _TrendAction:
    fetch: Callable[[TrendAnalysisSpec], list[dict[str, Any]]]
    item_type: type[BaseModel]
    message: str


class TrendService:
    def __init__(self, dao: PriceTrendDao) -> None:
        self.dao = dao

    def handle(self, slots: TrendSlots) -> TrendResult:
        criteria: TrendAnalysisSpec | None = None
        try:
            criteria = normalize_trend_policy(slots)
            action = self._action(criteria.analysis_type)
            rows = action.fetch(criteria)
            if not rows:
                raise TrendError("no_result", "조건에 맞는 시세 데이터를 찾지 못했습니다.")

            results = [action.item_type(**row) for row in rows]
            return TrendResult.ok(
                analysis_type=criteria.analysis_type,
                criteria=_criteria(criteria),
                calculation=_calculation(criteria, results),
                units=_units(criteria),
                results=results,
                message=action.message,
            )
        except TrendError as error:
            return TrendResult.fail(
                analysis_type=slots.analysis_type,
                reason=error.reason,
                message=error.message,
                criteria=criteria,
                candidates=error.candidates,
                slots=slots.model_dump(mode="json", exclude_none=True),
            )

    def _action(self, analysis_type: str) -> _TrendAction:
        if analysis_type == ANALYSIS_TIMESERIES:
            return _TrendAction(self.dao.find_timeseries, TrendPoint, "시세추이를 조회했습니다.")
        if analysis_type == ANALYSIS_RANKING:
            return _TrendAction(self.dao.find_ranking, PriceChangeRankingItem, "가격 순위를 조회했습니다.")
        raise TrendError("invalid_request", "지원하지 않는 분석 유형입니다.")


def run_price_trend(session: Session, slots: dict[str, Any], query: str = "") -> dict[str, Any]:
    payload = dict(slots)
    if query and payload.get("original_question") is None:
        payload["original_question"] = query

    try:
        request = TrendSlots(**payload)
    except ValidationError as error:
        result = TrendResult.fail(
            analysis_type=payload.get("analysis_type"),
            reason="invalid_request",
            message="시세추이 요청 슬롯 형식이 올바르지 않습니다.",
            slots={key: value for key, value in payload.items() if value is not None},
        ).model_dump(mode="json", exclude_none=True)
        return {"handler": "price_trend", **result, "errors": _validation_errors(error)}

    result = TrendService(PriceTrendDao(session)).handle(request)
    return {"handler": "price_trend", **result.model_dump(mode="json", exclude_none=True)}


def _criteria(criteria: TrendAnalysisSpec) -> dict[str, Any]:
    values: dict[str, Any] = {
        "analysis_type": criteria.analysis_type,
        "target_type": criteria.target_type,
        "target_name": criteria.target_name,
        "start_date": criteria.start_date,
        "end_date": criteria.end_date,
    }
    for key in ("area_min", "area_max", "interval", "rank_by", "direction", "limit"):
        value = getattr(criteria, key)
        if value is not None:
            values[key] = value
    return values


def _calculation(criteria: TrendAnalysisSpec, results: list[TrendData]) -> dict[str, Any] | None:
    if criteria.analysis_type == ANALYSIS_RANKING:
        return _ranking_calculation(criteria)

    points = [item for item in results if isinstance(item, TrendPoint)]
    first = points[0]
    last = points[-1]
    metric = "avg_deal_amount" if criteria.area_min is not None else "avg_price_per_sqm"
    first_value = float(getattr(first, metric))
    last_value = float(getattr(last, metric))
    change = last_value - first_value
    return {
        "primary_metric": metric,
        "first_period": first.period_start,
        "last_period": last.period_start,
        "first_value": round(first_value, 2),
        "last_value": round(last_value, 2),
        "change_amount": round(change, 2),
        "change_rate": None if first_value == 0 else round(change / first_value * 100, 2),
        "observed_period_count": len(points),
        "total_trade_count": sum(point.trade_count for point in points),
    }


def _ranking_calculation(criteria: TrendAnalysisSpec) -> dict[str, Any]:
    if criteria.rank_by != "change_rate":
        return {"metric": criteria.rank_by, "direction": criteria.direction}
    return {
        "metric": "price_per_sqm",
        "min_trade_count": criteria.min_trade_count,
        "start_window": {
            "start_date": criteria.start_window_start,
            "end_date": criteria.start_window_end,
        },
        "end_window": {
            "start_date": criteria.end_window_start,
            "end_date": criteria.end_window_end,
        },
    }


def _units(criteria: TrendAnalysisSpec) -> dict[str, str]:
    if criteria.analysis_type == ANALYSIS_RANKING and criteria.rank_by != "change_rate":
        return {"deal_amount": "만원"}
    return {"deal_amount": "만원", "price_per_sqm": "만원/㎡"}


def _validation_errors(error: ValidationError) -> list[dict[str, Any]]:
    return [
        {"loc": list(item["loc"]), "msg": item["msg"], "type": item["type"]}
        for item in error.errors()
    ]
