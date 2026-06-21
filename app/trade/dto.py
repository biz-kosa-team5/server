from __future__ import annotations

from pydantic import BaseModel, Field


class TradeItemResponse(BaseModel):
  trade_id: int = Field(alias="tradeId")
  deal_date: str = Field(alias="dealDate")
  excl_area: float = Field(alias="exclArea")
  deal_amount: int = Field(alias="dealAmount")
  apt_dong: str | None = Field(alias="aptDong")
  floor: int | None


class TradePageResponse(BaseModel):
  parcel_id: int = Field(alias="parcelId")
  complex_id: int | None = Field(alias="complexId")
  content: list[TradeItemResponse]
  page: int
  size: int
  total_elements: int = Field(alias="totalElements")
  total_pages: int = Field(alias="totalPages")


class TradeTrendPointResponse(BaseModel):
  month: str
  avg_amount: float = Field(alias="avgAmount")
  count: int
  min_amount: int = Field(alias="minAmount")
  max_amount: int = Field(alias="maxAmount")
