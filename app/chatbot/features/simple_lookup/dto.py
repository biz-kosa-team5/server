"""simple_lookup DTO 정의."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Mapping, TypeAlias

from pydantic import BaseModel, ConfigDict, Field


# query_type 상수
QUERY_LOCATION = "location"
QUERY_TRADE_HISTORY = "trade_history"
QUERY_REGION_TRADE_HISTORY = "region_trade_history"
QUERY_COMPLEX_PRICE_RECORD = "complex_price_record"
QUERY_REGION_PRICE_RANKING = "region_price_ranking"

# 정렬 상수
SORT_LATEST = "latest"
SORT_OLDEST = "oldest"

# 가격 정렬 상수
PRICE_HIGHEST = "highest"
PRICE_LOWEST = "lowest"

DEFAULT_LOOKUP_UNITS: dict[str, str] = {
    "deal_amount": "만원",
    "excl_area": "㎡",
    "price_per_m2": "만원/㎡",
}


# 허용 query_type
QueryType: TypeAlias = Literal[
    "location",
    "trade_history",
    "region_trade_history",
    "complex_price_record",
    "region_price_ranking",
]

# 허용 정렬값
SortOrder: TypeAlias = Literal["latest", "oldest"]
PriceOrder: TypeAlias = Literal["highest", "lowest"]


class SimpleLookupError(ValueError):
    # 단순조회 업무 예외

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


class SimpleLookupSlots(BaseModel):
    # LLM/tool에서 받은 원본 슬롯

    model_config = ConfigDict(extra="ignore")

    query_type: QueryType
    target_name: str

    area: float | None = Field(default=None, gt=0)
    pyeong: float | None = Field(default=None, gt=0)

    period: str | None = Field(default=None, pattern=r"^[1-9]\d*(m|y)$")
    start_date: date | None = None
    end_date: date | None = None

    limit: int | None = Field(default=None, gt=0)
    sort_order: SortOrder | None = None
    price_order: PriceOrder | None = None

    original_question: str | None = None


class SimpleLookupCriteria(BaseModel):
    # policy에서 정규화한 DAO 조회 조건

    model_config = ConfigDict(frozen=True)

    query_type: QueryType
    target_name: str
    target_type: str | None = None

    area_min: float | None = None
    area_max: float | None = None

    start_date: date | None = None
    end_date: date | None = None

    limit: int | None = None
    sort_order: SortOrder | None = None
    price_order: PriceOrder | None = None


def _calculate_price_per_m2(
    deal_amount: int,
    excl_area: float | None,
) -> float | None:
    # ㎡당 가격 계산, 단위는 만원/㎡

    if not excl_area:
        return None

    return round(deal_amount / excl_area, 2)


class LocationData(BaseModel):
    # location 응답 데이터

    model_config = ConfigDict(extra="ignore")

    complex_id: int
    complex_name: str
    trade_name: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    @classmethod
    def from_complex(cls, complex_obj: Any) -> "LocationData":
        # Complex entity -> LocationData

        return cls(
            complex_id=complex_obj.id,
            complex_name=complex_obj.name,
            trade_name=complex_obj.trade_name,
            address=complex_obj.address,
            latitude=complex_obj.latitude,
            longitude=complex_obj.longitude,
        )


class TradeData(BaseModel):
    # trade_history, complex_price_record 공통 응답 데이터

    model_config = ConfigDict(extra="ignore")

    complex_id: int
    complex_name: str
    trade_name: str | None = None
    address: str | None = None

    trade_id: int
    deal_date: date
    deal_amount: int
    excl_area: float
    price_per_m2: float | None = None

    floor: int | None = None
    apt_dong: str | None = None

    @classmethod
    def from_trade(
        cls,
        trade: Any,
        complex_obj: Any,
    ) -> "TradeData":
        # Trade entity + Complex entity -> TradeData

        return cls(
            complex_id=complex_obj.id,
            complex_name=complex_obj.name,
            trade_name=complex_obj.trade_name,
            address=complex_obj.address,
            trade_id=trade.id,
            deal_date=trade.deal_date,
            deal_amount=trade.deal_amount,
            excl_area=trade.excl_area,
            price_per_m2=_calculate_price_per_m2(
                trade.deal_amount,
                trade.excl_area,
            ),
            floor=trade.floor,
            apt_dong=trade.apt_dong,
        )


class RegionRankingData(BaseModel):
    # region_price_ranking 응답 데이터

    model_config = ConfigDict(extra="ignore")

    rank: int
    region_name: str

    complex_id: int
    complex_name: str
    trade_name: str | None = None
    address: str | None = None

    trade_id: int
    deal_date: date
    deal_amount: int
    excl_area: float
    price_per_m2: float | None = None

    floor: int | None = None
    apt_dong: str | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "RegionRankingData":
        # raw SQL row -> RegionRankingData

        data = dict(row)
        data["price_per_m2"] = _calculate_price_per_m2(
            data["deal_amount"],
            data["excl_area"],
        )

        return cls.model_validate(data)


# 성공 응답 data에 들어갈 수 있는 항목 타입
LookupItemData: TypeAlias = LocationData | TradeData | RegionRankingData


class SimpleLookupObservation(BaseModel):
    # 단순조회 성공 응답

    handler: str = "simple_lookup"
    success: Literal[True] = True
    query_type: QueryType
    criteria: dict[str, Any] = Field(default_factory=dict)
    units: dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_LOOKUP_UNITS))
    data: list[LookupItemData] = Field(default_factory=list)


class SimpleLookupFailure(BaseModel):
    # 단순조회 실패 응답

    handler: str = "simple_lookup"
    success: Literal[False] = False
    query_type: str | None = None
    criteria: dict[str, Any] = Field(default_factory=dict)

    reason: str
    message: str
    candidates: list[dict[str, Any]] = Field(default_factory=list)


# 단순조회 최종 응답 타입
SimpleLookupResponse: TypeAlias = SimpleLookupObservation | SimpleLookupFailure
