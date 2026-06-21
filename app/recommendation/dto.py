from __future__ import annotations

from pydantic import BaseModel


class RecommendationSlots(BaseModel):
  district: str | None = None
  station_name: str | None = None
  school_name: str | None = None
  school_type: str | None = None
  max_price: int | None = None
  min_price: int | None = None
  min_households: int | None = None
  min_pyeong: float | None = None
  is_new_build: bool | None = None
  min_built_year: int | None = None
  radius_m: int | None = None
  sort_by: str | None = None
  limit: int | None = None

