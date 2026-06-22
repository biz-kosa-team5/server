from __future__ import annotations

from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.chatbot.features.simple_lookup.dao import SimpleLookupDao
from app.chatbot.features.simple_lookup.dto import (
    QUERY_LOCATION,
    QUERY_RECORD_HIGH,
    QUERY_TRADE_HISTORY,
    SimpleLookupCriteria,
    SimpleLookupError,
    SimpleLookupResult,
    SimpleLookupSlots,
)
from app.chatbot.features.simple_lookup.policy import normalize_simple_lookup_policy


class SimpleLookupService:
    def __init__(self, dao: SimpleLookupDao) -> None:
        self.dao = dao

    def handle(self, slots: SimpleLookupSlots) -> SimpleLookupResult:
        criteria: SimpleLookupCriteria | None = None

        try:
            criteria = normalize_simple_lookup_policy(slots)

            if criteria.query_type == QUERY_LOCATION:
                data = self.dao.find_location(criteria)
                return SimpleLookupResult.ok(
                    query_type=criteria.query_type,
                    criteria=criteria,
                    data=data,
                    message="단지 위치를 조회했습니다.",
                )

            if criteria.query_type == QUERY_TRADE_HISTORY:
                data = self.dao.find_trade_history(criteria)
                return SimpleLookupResult.ok(
                    query_type=criteria.query_type,
                    criteria=criteria,
                    data=data,
                    message="실거래 내역을 조회했습니다.",
                )

            if criteria.query_type == QUERY_RECORD_HIGH:
                data = self.dao.find_record_high(criteria)
                return SimpleLookupResult.ok(
                    query_type=criteria.query_type,
                    criteria=criteria,
                    data=data,
                    message="최고가 거래를 조회했습니다.",
                )

            raise SimpleLookupError(
                "invalid_request",
                "지원하지 않는 조회 유형입니다.",
            )

        except SimpleLookupError as error:
            return SimpleLookupResult.fail(
                query_type=slots.query_type,
                reason=error.reason,
                message=error.message,
                criteria=criteria,
                candidates=error.candidates,
            )


def run_simple_lookup(session: Session, slots: dict[str, Any], _: str = "") -> dict[str, Any]:
    try:
        request = SimpleLookupSlots(**slots)
    except ValidationError:
        return SimpleLookupResult.fail(
            query_type=slots.get("query_type"),
            reason="invalid_request",
            message="단순 조회 요청 슬롯이 올바르지 않습니다.",
        ).model_dump(mode="json")

    result = SimpleLookupService(SimpleLookupDao(session)).handle(request)
    return result.model_dump(mode="json")
