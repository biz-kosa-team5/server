from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


QUERY_LOCATION = "location"
QUERY_TRADE_HISTORY = "trade_history"
QUERY_RECORD_HIGH = "record_high"

SUPPORTED_QUERY_TYPES = { QUERY_LOCATION, QUERY_TRADE_HISTORY, QUERY_RECORD_HIGH }


class SimpleLookupError(ValueError):
    def __init__(self, reason: str, message: str, *, candidates: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.candidates = candidates or []


class SimpleLookupSlots(BaseModel):
    model_config = ConfigDict(extra="ignore")

    query_type: str
    complex_name: str

    area: float | None = None
    pyeong: int | None = None

    period: str | None = None
    start_date: date | None = None
    end_date: date | None = None

    limit: int | None = None
    original_question: str | None = None


class SimpleLookupCriteria(BaseModel):
    model_config = ConfigDict(frozen=True)

    query_type: str
    complex_name: str

    area_min: float | None = None
    area_max: float | None = None

    start_date: date | None = None
    end_date: date | None = None

    limit: int | None = None


class SimpleLookupResult(BaseModel):
    handler: str = "simple_lookup"
    success: bool
    query_type: str | None = None
    criteria: dict[str, Any] = Field(default_factory=dict)
    data: list[dict[str, Any]] = Field(default_factory=list)
    reason: str | None = None
    message: str = ""
    candidates: list[dict[str, Any]] = Field(default_factory=list)

    @classmethod
    def ok(cls, *, query_type: str, criteria: SimpleLookupCriteria, data: list[dict[str, Any]], message: str) -> "SimpleLookupResult":
        return cls(
            success=True,
            query_type=query_type,
            criteria=criteria.model_dump(mode="json"),
            data=data,
            message=message,
        )

    @classmethod
    def fail(
        cls,
        *,
        query_type: str | None,
        reason: str,
        message: str,
        criteria: SimpleLookupCriteria | None = None,
        candidates: list[dict[str, Any]] | None = None,
    ) -> "SimpleLookupResult":
        return cls(
            success=False,
            query_type=query_type,
            criteria=criteria.model_dump(mode="json") if criteria else {},
            reason=reason,
            message=message,
            candidates=candidates or [],
        )
