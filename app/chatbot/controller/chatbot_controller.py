from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.chatbot.dto import ChatbotQueryRequest
from app.chatbot.service.chatbot_service import handle_chatbot_query
from app.database import get_session


router = APIRouter(tags=["chatbot"])


@router.post("/chatbot/query")
def query_by_natural_language(
  payload: ChatbotQueryRequest = Body(...),
  session: Session = Depends(get_session),
) -> dict[str, Any]:
  return handle_chatbot_query(session, payload.question)
