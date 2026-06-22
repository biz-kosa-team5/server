from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from ...handler.base import HandlerResult
from ...types import FragmentStatus
from .rag.dao import LegalRagQueryDao
from .rag.service.query import LegalRagQueryService


LegalRagServiceFactory = Callable[[Session], LegalRagQueryService]


class LegalContractHandler:
  def __init__(self, service_factory: LegalRagServiceFactory | None = None):
    self.service_factory = service_factory or self.default_service

  def handle(self, session: Session, text: str) -> HandlerResult:
    result = self.service_factory(session).query(text)
    return HandlerResult(
      status=FragmentStatus.HANDLED,
      slots={},
      result=result,
    )

  @staticmethod
  def default_service(session: Session) -> LegalRagQueryService:
    return LegalRagQueryService(LegalRagQueryDao(session))
