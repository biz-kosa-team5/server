from __future__ import annotations

from pydantic import BaseModel, Field


class EmbeddingRequest(BaseModel):
  batch_size: int = Field(default=100, alias="batchSize", ge=1, le=500)
  retry_failed: bool = Field(default=False, alias="retryFailed")
  limit: int | None = Field(default=None, ge=1)


class EmbeddingSummary(BaseModel):
  candidates: int
  embedded: int
  failed: int
  skipped: int
  model: str
  dimensions: int


class EmbeddingStatusItem(BaseModel):
  status: str
  count: int


class EmbeddingStatusResponse(BaseModel):
  total: int
  with_embedding: int = Field(alias="withEmbedding")
  without_embedding: int = Field(alias="withoutEmbedding")
  statuses: list[EmbeddingStatusItem]
