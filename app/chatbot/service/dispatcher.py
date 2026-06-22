from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.chatbot.dto import Intent

from .handler import GenericIntentHandler
from .registry import get_feature_spec


GENERIC_HANDLER = GenericIntentHandler()


def dispatch_text(session: Session, intent: Intent, text: str):
  return GENERIC_HANDLER.handle(session, text, get_feature_spec(intent))


def dispatch_slots(session: Session, intent: Intent, slots: dict[str, Any], text: str = ""):
  return GENERIC_HANDLER.handle_slots(session, slots, text, get_feature_spec(intent))


def parse_intent(value: Any) -> Intent:
  try:
    return Intent(str(value).strip())
  except (TypeError, ValueError):
    return Intent.UNSUPPORTED
