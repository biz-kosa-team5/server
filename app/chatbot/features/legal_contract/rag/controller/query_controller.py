from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_session
from ..dao import LegalRagQueryDao
from ..dto.query import LegalRagQueryRequest, LegalRagQueryResponse
from ..service.query import LegalRagQueryService


router = APIRouter(tags=["legal-rag-query"])


@router.post("/api/laws/query", response_model=LegalRagQueryResponse)
def query_law_sources(
  request: LegalRagQueryRequest,
  session: Session = Depends(get_session),
) -> dict[str, Any]:
  service = LegalRagQueryService(LegalRagQueryDao(session))
  return service.query(request.question, request.top_k)
