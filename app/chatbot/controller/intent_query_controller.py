from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from ...database import get_session
from ..dto.intent_query_dto import QueryRequest
from ..service import intent_dispatch_service


router = APIRouter(prefix="/api/v1", tags=["query"])


@router.post("/query")
def query_by_intent(
  payload: QueryRequest = Body(default=QueryRequest()),
  session: Session = Depends(get_session),
) -> dict[str, Any]:
  # 자연어가 아니라, 앞 단계에서 완성된 intent + slots JSON만 받는다.
  return intent_dispatch_service.handle_query(session, payload)

