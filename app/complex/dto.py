from __future__ import annotations

from pydantic import BaseModel, Field


class ComplexDetailResponse(BaseModel):
  parcel_id: int = Field(alias="parcelId")
  complex_id: int = Field(alias="complexId")
  latitude: float | None
  longitude: float | None
  address: str | None
  trade_name: str | None = Field(alias="tradeName")
  name: str
  dong_cnt: int | None = Field(alias="dongCnt")
  unit_cnt: int | None = Field(alias="unitCnt")
  plat_area: float | None = Field(alias="platArea")
  arch_area: float | None = Field(alias="archArea")
  tot_area: float | None = Field(alias="totArea")
  bc_rat: float | None = Field(alias="bcRat")
  vl_rat: float | None = Field(alias="vlRat")
  use_date: str | None = Field(alias="useDate")


class ParcelComplexResponse(BaseModel):
  complex_id: int = Field(alias="complexId")
  complex_name: str = Field(alias="complexName")
  parcel_id: int = Field(alias="parcelId")
  latitude: float | None
  longitude: float | None
  address: str | None
  dong_cnt: int | None = Field(alias="dongCnt")
  unit_cnt: int | None = Field(alias="unitCnt")
  use_date: str | None = Field(alias="useDate")
