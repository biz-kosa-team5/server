from __future__ import annotations

import json
import os
from typing import Any, Protocol

from openai import OpenAI

from ..dto.answer import LegalAnswerDraft


DEFAULT_ANSWER_MODEL = "gpt-5.5"

ANSWER_RESPONSE_FORMAT = {
  "type": "json_schema",
  "json_schema": {
    "name": "legal_answer",
    "strict": True,
    "schema": {
      "type": "object",
      "properties": {
        "answer": {"type": ["string", "null"]},
        "citedDocumentIds": {
          "type": "array",
          "items": {"type": "integer"},
        },
        "status": {
          "type": "string",
          "enum": ["answered", "insufficient_evidence"],
        },
      },
      "required": ["answer", "citedDocumentIds", "status"],
      "additionalProperties": False,
    },
  },
}


class LegalAnswerGenerator(Protocol):
  def generate(self, messages: list[dict[str, str]]) -> LegalAnswerDraft:
    ...


class OpenAILegalAnswerGenerator:
  def __init__(
    self,
    api_key: str | None = None,
    model: str | None = None,
    client: Any | None = None,
  ):
    self.api_key = api_key
    self.model = model or os.getenv("OPENAI_CHAT_MODEL", DEFAULT_ANSWER_MODEL)
    self._client = client

  def generate(self, messages: list[dict[str, str]]) -> LegalAnswerDraft:
    client = self._client or self._openai_client()
    response = client.chat.completions.create(
      model=self.model,
      messages=messages,
      response_format=ANSWER_RESPONSE_FORMAT,
    )
    content = response.choices[0].message.content
    if not content:
      raise ValueError("OpenAI returned an empty legal answer")
    return LegalAnswerDraft.model_validate(json.loads(content))

  def _openai_client(self) -> OpenAI:
    resolved_key = self.api_key or os.getenv("OPENAI_API_KEY", "")
    if not resolved_key:
      raise ValueError("OPENAI_API_KEY environment variable is required")
    return OpenAI(api_key=resolved_key)
