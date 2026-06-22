from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IntentQueryRequest(BaseModel):
  intent: str | None = None
  slots: dict[str, Any] = Field(default_factory=dict)
