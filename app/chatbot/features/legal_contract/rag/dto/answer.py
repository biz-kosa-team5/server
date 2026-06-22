from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from .query import LegalSourceResponse


class LegalAnswerStatus(str, Enum):
  ANSWERED = "answered"
  INSUFFICIENT_EVIDENCE = "insufficient_evidence"
  GENERATION_FAILED = "generation_failed"


class LegalAnswerDraft(BaseModel):
  model_config = ConfigDict(populate_by_name=True)

  answer: str | None
  cited_document_ids: list[int] = Field(alias="citedDocumentIds")
  status: LegalAnswerStatus


class LegalCitation(BaseModel):
  model_config = ConfigDict(populate_by_name=True)

  document_id: int = Field(alias="documentId")
  law_name: str = Field(alias="lawName")
  article_no: str = Field(alias="articleNo")
  article_title: str | None = Field(alias="articleTitle")
  paragraph_no: str = Field(alias="paragraphNo")
  source_url: str | None = Field(alias="sourceUrl")
  effective_date: str = Field(alias="effectiveDate")


class LegalAnswerResponse(BaseModel):
  model_config = ConfigDict(populate_by_name=True)

  handler: str = "legal_contract"
  success: bool
  question: str
  expanded_terms: list[str] = Field(alias="expandedTerms")
  answer: str | None
  answer_status: LegalAnswerStatus = Field(alias="answerStatus")
  citations: list[LegalCitation]
  sources: list[LegalSourceResponse]
  retrieval_score: float | None = Field(alias="retrievalScore")
  reason: str | None = None
  message: str
