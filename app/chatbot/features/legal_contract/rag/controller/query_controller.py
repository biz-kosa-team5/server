from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..dto.query import LegalRagQueryRequest, LegalRagQueryResponse
from .dependencies import LegalRagQueryServiceDep


router = APIRouter(tags=["legal-rag-query"])


@router.post("/api/laws/query", response_model=LegalRagQueryResponse)
def query_law_sources(
  request: LegalRagQueryRequest,
  service: LegalRagQueryServiceDep,
) -> dict[str, Any]:
  return service.query(request.question, request.top_k)
