from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from .normalization import normalize_query
from .rag.dao import LegalRagQueryDao
from .rag.service.query_service import LegalRagQueryService


LegalRagServiceFactory = Callable[[Session], LegalRagQueryService]


def default_legal_rag_service(session: Session) -> LegalRagQueryService:
  return LegalRagQueryService(LegalRagQueryDao(session))


def run_legal_contract(
  session: Session,
  slots: dict[str, Any],
  text: str = "",
  service_factory: LegalRagServiceFactory = default_legal_rag_service,
) -> dict[str, Any]:
  original_query = str(slots.get("original_query") or text)
  normalized_query = normalize_query(original_query)
  slots["original_query"] = original_query
  slots["normalized_query"] = normalized_query

  result = service_factory(session).query(normalized_query)
  slots["expanded_terms"] = list(result.get("expandedTerms", []))
  return result
