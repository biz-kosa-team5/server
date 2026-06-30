from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatbotQueryRequest(BaseModel):
  question: str = Field(min_length=1)
  conversationContext: dict[str, Any] | None = None

  @field_validator("question")
  @classmethod
  def normalize_question(cls, value: str) -> str:
    question = value.strip()
    if not question:
      raise ValueError("질문을 입력해 주세요.")
    return question


class ChatbotQueryResponse(BaseModel):
  model_config = ConfigDict(extra="allow")

  success: bool
  status: str
  question: str
  fragments: list[dict[str, Any]]
  result: Any
  message: str
  executionSummary: dict[str, Any]
  answer: str
  resolvedQuestion: str | None = None
  conversationResolution: dict[str, Any] | None = None
  conversationMemoryPatch: dict[str, Any] | None = None
  uiActions: list[dict[str, Any]] = Field(default_factory=list)
  uiArtifacts: list[dict[str, Any]] = Field(default_factory=list)
  uiSummary: dict[str, Any] | None = None
