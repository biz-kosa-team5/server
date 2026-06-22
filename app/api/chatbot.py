from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..chatbot.service.chatbot_service import handle_chatbot_query
from ..chatbot.service.intent_dispatch_service import handle_query
from ..database import get_session


router = APIRouter(prefix="/api/v1")


class ChatbotQueryRequest(BaseModel):
  question: str = Field(min_length=1)


class IntentQueryRequest(BaseModel):
  intent: str | None = None
  slots: dict[str, Any] = Field(default_factory=dict)


@router.post("/query", tags=["query"])
def query_by_intent(
  payload: IntentQueryRequest = Body(default=IntentQueryRequest()),
  session: Session = Depends(get_session),
) -> dict[str, Any]:
  return handle_query(session, payload.intent, payload.slots)


@router.post("/chatbot/query", tags=["chatbot"])
def query_by_natural_language(
  payload: ChatbotQueryRequest = Body(...),
  session: Session = Depends(get_session),
) -> dict[str, Any]:
  return handle_chatbot_query(session, payload.question)
