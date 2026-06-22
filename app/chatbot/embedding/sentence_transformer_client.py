from __future__ import annotations

import os
from typing import Any


DEFAULT_SENTENCE_TRANSFORMER_MODEL = "BAAI/bge-m3"


class SentenceTransformerEmbeddingClient:
  def __init__(self, model: str | None = None):
    self.model = model or os.getenv(
      "CHATBOT_INTENT_EMBEDDING_MODEL",
      DEFAULT_SENTENCE_TRANSFORMER_MODEL,
    )
    self._encoder: Any | None = None
    self._dimensions: int | None = None

  @property
  def dimensions(self) -> int:
    if self._dimensions is None:
      self._dimensions = int(self._load_model().get_sentence_embedding_dimension() or 0)
    return self._dimensions

  def prepare_text(self, text: str) -> str:
    return text.strip()

  def embed(self, texts: list[str]) -> list[list[float]]:
    if not texts:
      return []

    encoded = self._load_model().encode(
      texts,
      convert_to_numpy=True,
      normalize_embeddings=False,
    )
    vectors = encoded.tolist()
    if len(vectors) != len(texts):
      raise ValueError("SentenceTransformer returned an unexpected number of embeddings")
    if vectors:
      self._dimensions = len(vectors[0])
    return vectors

  def _load_model(self) -> Any:
    if self._encoder is None:
      from sentence_transformers import SentenceTransformer

      self._encoder = SentenceTransformer(self.model)
    return self._encoder
