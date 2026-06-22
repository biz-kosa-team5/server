from __future__ import annotations

from typing import Protocol


class EmbeddingClient(Protocol):
  model: str

  @property
  def dimensions(self) -> int:
    ...

  def prepare_text(self, text: str) -> str:
    ...

  def embed(self, texts: list[str]) -> list[list[float]]:
    ...
