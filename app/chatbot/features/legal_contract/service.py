from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from .rag.dao import LegalRagQueryDao
from .rag.service.query_service import LegalRagQueryService


LegalRagServiceFactory = Callable[[Session], LegalRagQueryService]


def default_legal_rag_service(session: Session) -> LegalRagQueryService:
  return LegalRagQueryService(LegalRagQueryDao(session))


def run_legal_contract(
  session: Session,
  _: dict[str, Any],
  text: str = "",
  service_factory: LegalRagServiceFactory = default_legal_rag_service,
) -> dict[str, Any]:
  return service_factory(session).query(text)
