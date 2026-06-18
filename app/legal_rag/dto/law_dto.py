from __future__ import annotations

from pydantic import BaseModel, Field


class LawIngestRequest(BaseModel):
  keywords: list[str] | None = None


class LawParseRequest(BaseModel):
  raw_ids: list[int] | None = Field(default=None, alias="rawIds")


class TermIngestRequest(BaseModel):
  keywords: list[str] | None = None


class OperationSummary(BaseModel):
  processed: int
  succeeded: int
  failed: int


class ParseSummary(OperationSummary):
  documents_saved: int


class MappingParseSummary(OperationSummary):
  mappings_saved: int

