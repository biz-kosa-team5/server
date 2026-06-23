"""시세추이와 가격 변화 조회 흐름."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.chatbot.features.price_trend.dao import PriceTrendDao
from app.chatbot.features.price_trend.dto import (
    QUERY_COMPLEX_TREND,
    QUERY_PRICE_CHANGE_RANKING,
    QUERY_REGION_TREND,
    PriceChangeRankingItem,
    TrendCriteria,
    TrendData,
    TrendError,
    TrendPoint,
    TrendResult,
    TrendSlots,
)
from app.chatbot.features.price_trend.policy import normalize_trend_policy


@dataclass(frozen=True)
class _TrendAction:
    """query_type별 DAO 호출과 응답 변환 정보를 묶는다."""

    fetch: Callable[[TrendCriteria], list[dict[str, Any]]]
    item_type: type[BaseModel]
    success_message: str


class TrendService:
    """H4 시세추이 query_type을 실행한다."""

    def __init__(self, dao: PriceTrendDao) -> None:
        self.dao = dao

    def handle(self, slots: TrendSlots) -> TrendResult:
        """슬롯을 Criteria로 정규화한 뒤 query_type별 DAO 함수를 실행한다."""

        criteria: TrendCriteria | None = None

        try:
            criteria = normalize_trend_policy(slots)
            action = self._resolve_action(criteria.query_type)
            rows = action.fetch(criteria)

            if not rows:
                raise TrendError(
                    "no_result",
                    "조건에 맞는 시세 데이터를 찾지 못했습니다.",
                )

            data = [action.item_type(**row) for row in rows]

            return TrendResult.ok(
                query_type=criteria.query_type,
                criteria=criteria,
                data=data,
                summary=_build_summary(criteria, data),
                message=action.success_message,
            )

        except TrendError as error:
            return TrendResult.fail(
                query_type=slots.query_type,
                reason=error.reason,
                message=error.message,
                criteria=criteria,
                candidates=error.candidates,
            )

    def _resolve_action(self, query_type: str) -> _TrendAction:
        """query_type에 맞는 DAO 함수와 응답 DTO를 반환한다."""

        actions = {
            QUERY_COMPLEX_TREND: _TrendAction(
                fetch=self.dao.find_complex_trend,
                item_type=TrendPoint,
                success_message="단지 시세추이를 조회했습니다.",
            ),
            QUERY_REGION_TREND: _TrendAction(
                fetch=self.dao.find_region_trend,
                item_type=TrendPoint,
                success_message="지역 시세추이를 조회했습니다.",
            ),
            QUERY_PRICE_CHANGE_RANKING: _TrendAction(
                fetch=self.dao.find_price_change_ranking,
                item_type=PriceChangeRankingItem,
                success_message="가격 변화율 순위를 조회했습니다.",
            ),
        }

        action = actions.get(query_type)
        if action is None:
            raise TrendError(
                "invalid_request",
                "지원하지 않는 시세추이 조회 유형입니다.",
            )

        return action


def run_price_trend(
    session: Session,
    slots: dict[str, Any],
    query: str = "",
) -> dict[str, Any]:
    """외부 파이프라인에서 H4를 호출하는 진입점."""

    payload = dict(slots)
    if query and payload.get("original_question") is None:
        payload["original_question"] = query

    try:
        request = TrendSlots(**payload)
    except ValidationError as error:
        result = TrendResult.fail(
            query_type=payload.get("query_type"),
            reason="invalid_request",
            message="시세추이 요청 슬롯이 올바르지 않습니다.",
        ).model_dump(mode="json")
        return {
            "handler": "price_trend",
            **result,
            "errors": _validation_errors(error),
        }

    result = TrendService(PriceTrendDao(session)).handle(request)
    return {
        "handler": "price_trend",
        **result.model_dump(mode="json"),
    }


def _build_summary(
    criteria: TrendCriteria,
    data: list[TrendData],
) -> dict[str, Any]:
    """query_type에 맞는 요약 정보를 생성한다."""

    if criteria.query_type == QUERY_PRICE_CHANGE_RANKING:
        first = data[0]
        assert isinstance(first, PriceChangeRankingItem)

        return {
            "change_direction": criteria.change_direction,
            "result_count": len(data),
            "top_change_rate": first.change_rate,
        }

    points = [item for item in data if isinstance(item, TrendPoint)]
    first_point = points[0]
    last_point = points[-1]

    primary_metric = (
        "avg_deal_amount"
        if criteria.area_min is not None
        else "avg_price_per_sqm"
    )
    first_value = float(getattr(first_point, primary_metric))
    last_value = float(getattr(last_point, primary_metric))
    change_amount = last_value - first_value

    return {
        "primary_metric": primary_metric,
        "first_period": first_point.period_start,
        "last_period": last_point.period_start,
        "first_value": round(first_value, 2),
        "last_value": round(last_value, 2),
        "change_amount": round(change_amount, 2),
        "change_rate": (
            None
            if first_value == 0
            else round(change_amount / first_value * 100, 2)
        ),
        "observed_period_count": len(points),
        "total_trade_count": sum(point.trade_count for point in points),
    }


def _validation_errors(error: ValidationError) -> list[dict[str, Any]]:
    """ValidationError에서 외부 응답에 필요한 필드만 반환한다."""

    return [
        {
            "loc": list(item["loc"]),
            "msg": item["msg"],
            "type": item["type"],
        }
        for item in error.errors()
    ]
