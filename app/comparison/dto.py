from __future__ import annotations

from pydantic import BaseModel, Field


class CompareSlots(BaseModel):
  apartment_names: list[str] = Field(default_factory=list)
  metrics: list[str] | None = None
  pyeong: float | None = None
  transaction_type: str | None = None
  period: str | None = None
  school_type: str | None = None
  school_name: str | None = None

