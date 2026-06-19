from __future__ import annotations

import os

import tiktoken
from openai import OpenAI


DEFAULT_MODEL = "text-embedding-3-large"
DEFAULT_DIMENSIONS = 1536
DEFAULT_MAX_INPUT_TOKENS = 8000


class OpenAIEmbeddingClient:
  def __init__(
    self,
    api_key: str | None = None,
    model: str | None = None,
    dimensions: int | None = None,
    max_input_tokens: int = DEFAULT_MAX_INPUT_TOKENS,
  ):
    resolved_key = api_key or os.getenv("OPENAI_API_KEY", "")
    if not resolved_key:
      raise ValueError("OPENAI_API_KEY environment variable is required")
    self.model = model or os.getenv("OPENAI_EMBEDDING_MODEL", DEFAULT_MODEL)
    self.dimensions = dimensions or int(
      os.getenv("OPENAI_EMBEDDING_DIMENSIONS", str(DEFAULT_DIMENSIONS))
    )
    if self.dimensions != DEFAULT_DIMENSIONS:
      raise ValueError(f"Embedding dimensions must be {DEFAULT_DIMENSIONS}")
    self.max_input_tokens = max_input_tokens
    self._client = OpenAI(api_key=resolved_key)
    self._encoding = tiktoken.get_encoding("cl100k_base")

  def prepare_text(self, text: str) -> str:
    tokens = self._encoding.encode(text)
    if len(tokens) <= self.max_input_tokens:
      return text
    return self._encoding.decode(tokens[:self.max_input_tokens])

  def embed(self, texts: list[str]) -> list[list[float]]:
    if not texts:
      return []
    response = self._client.embeddings.create(
      model=self.model,
      input=texts,
      dimensions=self.dimensions,
      encoding_format="float",
    )
    ordered = sorted(response.data, key=lambda item: item.index)
    vectors = [item.embedding for item in ordered]
    if len(vectors) != len(texts):
      raise ValueError("OpenAI returned an unexpected number of embeddings")
    if any(len(vector) != self.dimensions for vector in vectors):
      raise ValueError("OpenAI returned an embedding with an unexpected dimension")
    return vectors
