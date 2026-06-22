from __future__ import annotations

from pydantic import BaseModel, Field


class RegionMarkerResponse(BaseModel):
  id: int
  name: str
  lat: float
  lng: float
  unit_cnt_sum: int | None = Field(alias="unitCntSum")


class ComplexMarkerResponse(BaseModel):
  parcel_id: int = Field(alias="parcelId")
  complex_id: int = Field(alias="complexId")
  name: str
  lat: float
  lng: float
  latest_deal_amount: int | None = Field(alias="latestDealAmount")
  unit_cnt_sum: int | None = Field(alias="unitCntSum")
