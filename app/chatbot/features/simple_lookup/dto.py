from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# H1 단순조회에서 지원하는 조회 유형
QUERY_LOCATION = "location"
QUERY_TRADE_HISTORY = "trade_history"
QUERY_RECORD_HIGH = "record_high"

# H1에서 허용하는 query_type 목록
SUPPORTED_QUERY_TYPES = { QUERY_LOCATION, QUERY_TRADE_HISTORY, QUERY_RECORD_HIGH }

# H1 처리 중 발생하는 업무 실패를 표현하는 예외
class SimpleLookupError(ValueError):
    def __init__(self, reason: str, message: str, *, candidates: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.candidates = candidates or []

# 상위 파이프라인에서 전달받는 원본 슬롯 DTO
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

# Policy 검증 이후 DAO로 전달되는 조회 조건 DTO
class SimpleLookupCriteria(BaseModel):
    model_config = ConfigDict(frozen=True)

    query_type: str
    complex_name: str

    area_min: float | None = None
    area_max: float | None = None

    start_date: date | None = None
    end_date: date | None = None

    limit: int | None = None

# H1 단순조회의 성공/실패 공통 응답 DTO
class SimpleLookupResult(BaseModel):
    handler: str = "simple_lookup"
    success: bool
    query_type: str | None = None
    criteria: dict[str, Any] = Field(default_factory=dict)
    data: list[dict[str, Any]] = Field(default_factory=list)
    reason: str | None = None
    message: str = ""
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    
    # 성공 응답 생성
    @classmethod
    def ok(cls, *, query_type: str, criteria: SimpleLookupCriteria, data: list[dict[str, Any]], message: str) -> "SimpleLookupResult":
        return cls(
            success=True,
            query_type=query_type,
            criteria=criteria.model_dump(mode="json"),
            data=data,
            message=message,
        )
        
    # 실패 응답 생성
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
