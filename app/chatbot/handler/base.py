from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.orm import Session

from ..dto.chatbot_dto import FragmentStatus, Intent


@dataclass(frozen=True)
class HandlerResult:
  status: FragmentStatus
  slots: dict[str, Any]
  result: dict[str, Any]


class IntentHandler(Protocol):
  def handle(self, session: Session, text: str) -> HandlerResult:
    ...


def fragment_result(
  index: int,
  text: str,
  intent: Intent,
  status: FragmentStatus,
  slots: dict[str, Any],
  result: dict[str, Any],
  confidence: float | None = None,
) -> dict[str, Any]:
  return {
    "index": index,
    "text": text,
    "intent": intent.value,
    "status": status.value,
    "confidence": confidence,
    "slots": slots,
    "result": result,
  }
