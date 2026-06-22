from __future__ import annotations

from pydantic import BaseModel, Field


class LegalRagQueryRequest(BaseModel):
  question: str = Field(min_length=1)
  top_k: int = Field(default=5, alias="topK", ge=1, le=20)


class LegalSourceResponse(BaseModel):
  document_id: int = Field(alias="documentId")
  law_id: str = Field(alias="lawId")
  law_name: str = Field(alias="lawName")
  article_no: str = Field(alias="articleNo")
  article_title: str | None = Field(alias="articleTitle")
  paragraph_no: str = Field(alias="paragraphNo")
  content: str
  score: float
  source_url: str | None = Field(alias="sourceUrl")
  effective_date: str = Field(alias="effectiveDate")


class LegalRagQueryResponse(BaseModel):
  handler: str
  success: bool
  question: str
  expanded_terms: list[str] = Field(alias="expandedTerms")
  sources: list[LegalSourceResponse]
  summary: str | None = None
  reason: str | None = None
  message: str
