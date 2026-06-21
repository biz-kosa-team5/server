from __future__ import annotations

from pydantic import BaseModel, Field


class RegionSummaryResponse(BaseModel):
  id: int
  name: str


class RegionDetailResponse(BaseModel):
  id: int
  name: str
  latitude: float
  longitude: float
  children: list[RegionSummaryResponse]


class RegionComplexResponse(BaseModel):
  complex_id: int = Field(alias="complexId")
  complex_name: str = Field(alias="complexName")
  parcel_id: int = Field(alias="parcelId")
  latitude: float | None
  longitude: float | None
  address: str | None
  dong_cnt: int | None = Field(alias="dongCnt")
  unit_cnt: int | None = Field(alias="unitCnt")
  use_date: str | None = Field(alias="useDate")
