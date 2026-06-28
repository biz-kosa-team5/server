from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ChatbotQueryRequest(BaseModel):
  question: str = Field(min_length=1)

  @field_validator("question")
  @classmethod
  def normalize_question(cls, value: str) -> str:
    question = value.strip()
    if not question:
      raise ValueError("질문을 입력해 주세요.")
    return question
