from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.chatbot.dto import Intent

from .dispatcher import dispatch_slots, parse_intent


def handle_query(session: Session, intent: str | None, slots: dict[str, Any]) -> dict[str, Any]:
  parsed_intent = parse_intent(clean_text(intent) or Intent.UNSUPPORTED.value)
  return dispatch_slots(session, parsed_intent, slots).result


def clean_text(value: Any) -> str | None:
  if value is None:
    return None
  text = str(value).strip()
  if text == "" or text.lower() in {"none", "null"}:
    return None
  return text
