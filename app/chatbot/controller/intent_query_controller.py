from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.chatbot.dto import IntentQueryRequest
from app.chatbot.service.intent_dispatch_service import handle_query
from app.database import get_session


router = APIRouter(tags=["query"])


@router.post("/query")
def query_by_intent(
  payload: IntentQueryRequest = Body(default=IntentQueryRequest()),
  session: Session = Depends(get_session),
) -> dict[str, Any]:
  return handle_query(session, payload.intent, payload.slots)
