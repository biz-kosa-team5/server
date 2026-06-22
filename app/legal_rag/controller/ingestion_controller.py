from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...database import get_session
from ..client import LawApiClient
from ..dao import LegalDataDao
from ..schema.ingestion import (
  LawIngestRequest, LawParseRequest, MappingParseSummary, OperationSummary,
  ParseSummary, TermIngestRequest,
)
from ..service.ingestion import (
  LawCollectionService, LawParsingService, TermMappingCollectionService,
  TermMappingParsingService,
)


router = APIRouter(tags=["legal-rag-ingestion"])


@router.post("/api/laws/ingest/raw", response_model=OperationSummary)
def ingest_raw(request: LawIngestRequest, session: Session = Depends(get_session)):
  return LawCollectionService(LegalDataDao(session), LawApiClient()).ingest(request.keywords)


@router.post("/api/laws/parse", response_model=ParseSummary)
def parse_documents(request: LawParseRequest, session: Session = Depends(get_session)):
  return LawParsingService(LegalDataDao(session)).parse(request.raw_ids)


@router.post("/api/terms/ingest/raw", response_model=OperationSummary)
def ingest_term_raw(request: TermIngestRequest, session: Session = Depends(get_session)):
  return TermMappingCollectionService(LegalDataDao(session), LawApiClient()).ingest_raw(request.keywords)


@router.post("/api/terms/parse", response_model=MappingParseSummary)
def parse_term_raw(request: LawParseRequest, session: Session = Depends(get_session)):
  return TermMappingParsingService(LegalDataDao(session)).parse(request.raw_ids)


@router.get("/api/terms/raw")
def term_raw_list(query: str | None = None, limit: int = Query(50, ge=1, le=200),
  offset: int = Query(0, ge=0), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
  return [{"id": x.id, "sourceType": x.source_type, "target": x.target, "query": x.query,
    "requestUrl": x.request_url, "status": x.status, "errorMessage": x.error_message,
    "collectedAt": x.collected_at}
    for x in LegalDataDao(session).list_raw(query, "dlytrmRlt", limit, offset)]


@router.get("/api/laws/raw")
def raw_list(query: str | None = None, target: str | None = None, limit: int = Query(50, ge=1, le=200),
  offset: int = Query(0, ge=0), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
  return [{"id": x.id, "sourceType": x.source_type, "target": x.target, "query": x.query, "requestUrl": x.request_url,
    "status": x.status, "errorMessage": x.error_message, "collectedAt": x.collected_at}
    for x in LegalDataDao(session).list_raw(query, target, limit, offset)]


@router.get("/api/laws/documents")
def document_list(law_name: str | None = None, effective_date: date | None = None, parse_status: str | None = None,
  limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), session: Session = Depends(get_session)):
  return [{"id": x.id, "lawId": x.law_id, "lawName": x.law_name, "articleNo": x.article_no,
    "articleTitle": x.article_title, "paragraphNo": x.paragraph_no or None,
    "parentDocumentId": x.parent_document_id, "content": x.content,
    "effectiveDate": x.effective_date, "parseStatus": x.parse_status, "metadata": x.document_metadata, "sourceUrl": x.source_url}
    for x in LegalDataDao(session).list_documents(law_name, effective_date, parse_status, limit, offset)]


@router.get("/api/terms/mappings")
def mapping_list(daily_term: str | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
  session: Session = Depends(get_session)):
  return [{"id": x.id, "dailyTerm": x.daily_term, "legalTerm": x.legal_term, "relationType": x.relation_type,
    "domain": x.domain, "priority": x.priority, "rawData": x.raw_data}
    for x in LegalDataDao(session).list_mappings(daily_term, limit, offset)]
