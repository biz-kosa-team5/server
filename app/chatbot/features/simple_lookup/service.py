from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

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


@dataclass(frozen=True)
class _LookupAction:
    fetch: Callable[[SimpleLookupCriteria], list[dict[str, Any]]]
    success_message: str


class SimpleLookupService:
    def __init__(self, dao: SimpleLookupDao) -> None:
        self.dao = dao

    def handle(self, slots: SimpleLookupSlots) -> SimpleLookupResult:
        criteria: SimpleLookupCriteria | None = None

        try:
            criteria = normalize_simple_lookup_policy(slots)
            action = self._resolve_action(criteria.query_type)
            data = action.fetch(criteria)

            return SimpleLookupResult.ok(
                query_type=criteria.query_type,
                criteria=criteria,
                data=data,
                message=action.success_message,
            )
        except SimpleLookupError as error:
            return SimpleLookupResult.fail(
                query_type=slots.query_type,
                reason=error.reason,
                message=error.message,
                criteria=criteria,
                candidates=error.candidates,
            )

    def _resolve_action(self, query_type: str) -> _LookupAction:
        actions = {
            QUERY_LOCATION: _LookupAction(
                fetch=self.dao.find_location,
                success_message="단지 위치를 조회했습니다.",
            ),
            QUERY_TRADE_HISTORY: _LookupAction(
                fetch=self.dao.find_trade_history,
                success_message="실거래 내역을 조회했습니다.",
            ),
            QUERY_RECORD_HIGH: _LookupAction(
                fetch=self.dao.find_record_high,
                success_message="최고가 거래를 조회했습니다.",
            ),
        }

        action = actions.get(query_type)
        if action is None:
            raise SimpleLookupError(
                "invalid_request",
                "지원하지 않는 조회 유형입니다.",
            )
        return action


def run_simple_lookup(session: Session, slots: dict[str, Any], _: str = "") -> dict[str, Any]:
    try:
        request = SimpleLookupSlots(**slots)
    except ValidationError:
        return SimpleLookupResult.fail(
            query_type=slots.get("query_type"),
            reason="invalid_request",
            message="단순 조회 요청 슬롯 형식이 올바르지 않습니다.",
        ).model_dump(mode="json")

    result = SimpleLookupService(SimpleLookupDao(session)).handle(request)
    return result.model_dump(mode="json")
