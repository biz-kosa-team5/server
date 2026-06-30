"""price_trend service 모듈.

policy로 조회 조건을 만들고, DAO 조회 결과를 tool observation으로 반환한다.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .dao import PriceTrendDao
from .dto import (
    ANALYSIS_RANKING,
    ANALYSIS_TIMESERIES,
    TrendCriteria,
    TrendError,
    TrendFailObservation,
    TrendSuccessObservation,
)
from .policy import PriceTrendPolicy


class TrendService:
    """price_trend tool의 DB 조회 흐름을 담당한다."""

    def __init__(
        self,
        dao: PriceTrendDao | None = None,
        policy: PriceTrendPolicy | None = None,
    ) -> None:
        self.dao = dao or PriceTrendDao()
        self.policy = policy or PriceTrendPolicy()

    def handle(self, session: Session, slots: dict[str, Any]) -> dict[str, Any]:
        try:
            criteria = self.policy.build_criteria(slots)
            rows = self._fetch_rows(session, criteria)

            if not rows:
                return TrendFailObservation(
                    observation_type=criteria.get("analysis_type"),
                    reason="no_result",
                    message="조건에 맞는 시세추이 데이터가 없습니다.",
                    criteria=criteria,
                    slots=slots,
                ).model_dump(mode="json", exclude_none=True)

            return TrendSuccessObservation(
                observation_type=criteria["analysis_type"],
                criteria=criteria,
                summary_metrics=self._build_summary_metrics(criteria, rows),
                row_count=len(rows),
                rows=rows,
            ).model_dump(mode="json", exclude_none=True)

        except TrendError as error:
            return TrendFailObservation(
                reason=error.reason,
                message=error.message,
                candidates=error.candidates,
                slots=slots,
            ).model_dump(mode="json", exclude_none=True)

    # dao 호출 부분
    def _fetch_rows(self, session: Session, criteria: TrendCriteria) -> list[dict[str, Any]]:
        if criteria["analysis_type"] == ANALYSIS_TIMESERIES:
            return self.dao.find_timeseries(session, criteria)

        if criteria["analysis_type"] == ANALYSIS_RANKING:
            return self.dao.find_ranking(session, criteria)

        raise TrendError(
            "unsupported_query_type",
            "지원하지 않는 시세추이 분석 유형입니다.",
        )

    def _build_summary_metrics(
        self,
        criteria: TrendCriteria,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        metrics: dict[str, Any] = {
            "row_count": len(rows),
        }

        if criteria["analysis_type"] != ANALYSIS_TIMESERIES or not rows:
            return metrics

        first = rows[0]
        last = rows[-1]
        metrics.update(
            {
                "first_period": first.get("period_start"),
                "last_period": last.get("period_start"),
                "first_avg_deal_amount": first.get("avg_deal_amount"),
                "last_avg_deal_amount": last.get("avg_deal_amount"),
                "first_avg_price_per_sqm": first.get("avg_price_per_sqm"),
                "last_avg_price_per_sqm": last.get("avg_price_per_sqm"),
                "first_trade_count": first.get("trade_count"),
                "last_trade_count": last.get("trade_count"),
                "total_trade_count": sum(
                    int(row.get("trade_count") or 0)
                    for row in rows
                ),
            }
        )

        return metrics


def run_price_trend(session: Session, slots: dict[str, Any]) -> dict[str, Any]:
    """price_trend tool에서 호출하는 진입점."""

    return TrendService().handle(session, slots)
