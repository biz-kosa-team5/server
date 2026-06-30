"""simple_lookup 서비스 계층."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.chatbot.features.simple_lookup.dao import SimpleLookupDao
from app.chatbot.features.simple_lookup.dto import (
    LocationData,
    LookupItemData,
    QUERY_COMPLEX_PRICE_RECORD,
    QUERY_LOCATION,
    QUERY_REGION_PRICE_RANKING,
    QUERY_REGION_TRADE_HISTORY,
    QUERY_TRADE_HISTORY,
    RegionRankingData,
    SimpleLookupCriteria,
    SimpleLookupError,
    SimpleLookupFailure,
    SimpleLookupObservation,
    SimpleLookupResponse,
    SimpleLookupSlots,
    TradeData,
)
from app.chatbot.features.simple_lookup.policy import SimpleLookupPolicy


class SimpleLookupService:
    # 단순조회 실행 서비스

    def __init__(
        self,
        dao: SimpleLookupDao,
        policy: SimpleLookupPolicy | None = None,
    ) -> None:
        self.dao = dao
        self.policy = policy or SimpleLookupPolicy()

    def handle(self, slots: SimpleLookupSlots) -> SimpleLookupResponse:
        # 슬롯 -> criteria -> DAO 조회 -> 응답 DTO 변환

        criteria: SimpleLookupCriteria | None = None

        try:
            criteria = self.policy.build_criteria(slots)
            data = self._fetch_data(criteria)

            return SimpleLookupObservation(
                query_type=criteria.query_type,
                criteria=criteria.model_dump(
                    mode="json",
                    exclude_none=True,
                ),
                data=data,
            )

        except SimpleLookupError as error:
            return SimpleLookupFailure(
                query_type=slots.query_type,
                criteria=criteria.model_dump(
                    mode="json",
                    exclude_none=True,
                )
                if criteria
                else {},
                reason=error.reason,
                message=error.message,
                candidates=error.candidates,
            )

    # query_type별 DAO 호출 및 응답 데이터 변환
    def _fetch_data(self, criteria: SimpleLookupCriteria) -> list[LookupItemData]:
        if criteria.query_type == QUERY_LOCATION:
            complex_obj = self.dao.find_location(criteria)
            return [LocationData.from_complex(complex_obj)]

        if criteria.query_type == QUERY_TRADE_HISTORY:
            complex_obj, trades = self.dao.find_trade_history(criteria)
            return [TradeData.from_trade(trade, complex_obj) for trade in trades]

        if criteria.query_type == QUERY_REGION_TRADE_HISTORY:
            rows = self.dao.find_region_trade_history(criteria)
            return [
                TradeData.from_trade(row["trade"], row["complex"])
                for row in rows
            ]

        if criteria.query_type == QUERY_COMPLEX_PRICE_RECORD:
            complex_obj, trades = self.dao.find_complex_price_record(criteria)
            return [TradeData.from_trade(trade, complex_obj) for trade in trades]

        if criteria.query_type == QUERY_REGION_PRICE_RANKING:
            rows = self.dao.find_region_price_ranking(criteria)
            return [RegionRankingData.from_row(row) for row in rows]

        raise SimpleLookupError(
            "invalid_request",
            "지원하지 않는 단순조회 유형입니다.",
        )


# 단순조회 핸들러 진입점
def run_simple_lookup(
    session: Session,
    slots: dict[str, Any],
    _: str = "",
) -> dict[str, Any]:

    try:
        request = SimpleLookupSlots(**slots)

    except ValidationError:
        return SimpleLookupFailure(
            query_type=slots.get("query_type"),
            reason="invalid_request",
            message="단순 조회 요청 슬롯 형식이 올바르지 않습니다.",
        ).model_dump(mode="json")

    service = SimpleLookupService(
        dao=SimpleLookupDao(session),
    )
    result = service.handle(request)

    return result.model_dump(mode="json")
