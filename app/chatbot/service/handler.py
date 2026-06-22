from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.chatbot.dto import FragmentStatus, Intent


class SlotExtractor(Protocol):
  def __call__(self, text: str) -> dict[str, Any]:
    ...


class FeatureService(Protocol):
  def __call__(self, session: Session, slots: dict[str, Any], text: str = "") -> dict[str, Any]:
    ...


@dataclass(frozen=True)
class FeatureSpec:
  intent: Intent
  slot_extractor: SlotExtractor
  service: FeatureService
  default_status: FragmentStatus


@dataclass(frozen=True)
class HandlerResult:
  status: FragmentStatus
  slots: dict[str, Any]
  result: dict[str, Any]


class GenericIntentHandler:
  def handle(self, session: Session, text: str, spec: FeatureSpec) -> HandlerResult:
    slots = spec.slot_extractor(text)
    return self.handle_slots(session, slots, text, spec)

  def handle_slots(self, session: Session, slots: dict[str, Any], text: str, spec: FeatureSpec) -> HandlerResult:
    return HandlerResult(
      status=spec.default_status,
      slots=slots,
      result=spec.service(session, slots, text),
    )


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
