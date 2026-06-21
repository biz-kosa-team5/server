from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from ...database import get_session
from ..dto.chatbot_dto import ChatbotQueryRequest
from ..service.chatbot_service import handle_chatbot_query


router = APIRouter(prefix="/api/v1", tags=["chatbot"])


@router.post("/chatbot/query")
def query_by_natural_language(
  payload: ChatbotQueryRequest = Body(...),
  session: Session = Depends(get_session),
) -> dict[str, Any]:
  return handle_chatbot_query(session, payload)

