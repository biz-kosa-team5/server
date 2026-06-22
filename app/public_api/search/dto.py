from __future__ import annotations

from pydantic import BaseModel, Field


class ComplexSearchResponse(BaseModel):
  complex_id: int = Field(alias="complexId")
  complex_name: str = Field(alias="complexName")
  parcel_id: int = Field(alias="parcelId")
  latitude: float | None
  longitude: float | None
  address: str | None


class ComplexSuggestionResponse(BaseModel):
  complex_id: int = Field(alias="complexId")
  complex_name: str = Field(alias="complexName")
  parcel_id: int = Field(alias="parcelId")
  address: str | None
