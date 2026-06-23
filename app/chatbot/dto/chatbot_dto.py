from __future__ import annotations

from pydantic import BaseModel, Field


class ChatbotQueryRequest(BaseModel):
  question: str = Field(min_length=1)
