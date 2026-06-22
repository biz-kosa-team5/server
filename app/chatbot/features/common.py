from __future__ import annotations

from typing import Any


def normalize_slots(slots: dict[str, Any]) -> dict[str, Any]:
  # 문자열 "none", "null", ""는 조건 없음으로 보고 None으로 맞춘다.
  normalized: dict[str, Any] = {}
  for key, value in slots.items():
    if isinstance(value, str):
      normalized[key] = clean_text(value)
    elif isinstance(value, list):
      normalized[key] = [clean_text(item) if isinstance(item, str) else item for item in value]
    else:
      normalized[key] = value
  return normalized


def criteria_from_slots(slots: dict[str, Any]) -> dict[str, Any]:
  return {
    key: value
    for key, value in slots.items()
    if value not in (None, "", [])
  }


def empty_result(handler: str, reason: str, message: str, slots: dict[str, Any]) -> dict[str, Any]:
  return {
    "handler": handler,
    "success": False,
    "reason": reason,
    "criteria": criteria_from_slots(slots),
    "results": [],
    "message": message,
  }


def clean_text(value: Any) -> str | None:
  if value is None:
    return None
  text = str(value).strip()
  if text == "" or text.lower() in {"none", "null"}:
    return None
  return text
