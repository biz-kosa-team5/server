from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
  # intent는 어떤 service 로직을 실행할지 결정하고, slots는 쿼리 조건으로 사용한다.
  intent: str | None = None
  slots: dict[str, Any] = Field(default_factory=dict)
