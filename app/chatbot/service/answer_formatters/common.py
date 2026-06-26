from __future__ import annotations

from typing import Any


def format_failure_reason(result: Any) -> str:
  if not isinstance(result, dict):
    return ""
  message = clean_text(result.get("message"))
  if message:
    return message
  reason = clean_text(result.get("reason"))
  if reason:
    return f"처리하지 못한 이유는 {reason}입니다."
  return ""


def collect_result_messages(result: Any) -> list[str]:
  if isinstance(result, list):
    messages = []
    for item in result:
      messages.extend(collect_result_messages(item))
    return messages

  if not isinstance(result, dict):
    return []

  message = clean_text(result.get("message"))
  if message:
    return [message]

  nested_result = result.get("result")
  nested_messages = collect_result_messages(nested_result)
  if nested_messages:
    return nested_messages

  nested_results = result.get("results")
  nested_result_messages = collect_result_messages(nested_results)
  if nested_result_messages:
    return nested_result_messages

  handler = clean_text(result.get("handler") or result.get("agent"))
  status = clean_text(result.get("status"))
  reason = clean_text(result.get("reason"))
  if handler and status:
    return [status_message(status)]
  if handler:
    return ["조회 결과를 처리했습니다."]
  if status:
    return [status_message(status)]
  if reason:
    return [f"처리하지 못한 이유: {reason}"]
  return []


def status_message(status: str) -> str:
  messages = {
    "success": "조회 결과를 처리했습니다.",
    "partial_success": "일부 조회 결과만 처리했습니다.",
    "failed": "조회 결과를 처리하지 못했습니다.",
  }
  return messages.get(status, "조회 결과를 처리했습니다.")


def clean_text(value: Any) -> str:
  if not isinstance(value, str):
    return ""
  return value.strip()


def dict_value(value: Any) -> dict[str, Any]:
  return value if isinstance(value, dict) else {}


def list_value(value: Any) -> list[Any]:
  return value if isinstance(value, list) else []


def first_non_empty(values: list[str]) -> str:
  for value in values:
    if value:
      return value
  return ""


def compact_parts(values: list[Any]) -> list[str]:
  return [
    text
    for text in (clean_text(value) for value in values)
    if text and text != "정보 없음"
  ]


def format_labeled_value(label: str, value: Any, *, suffix: str = "") -> str:
  if value is None or value == "":
    return ""
  return f"{label} {value}{suffix}"


def format_floor(value: Any) -> str:
  if value is None or value == "":
    return ""
  return f"{value}층"


def format_price(value: Any) -> str:
  if value is None or value == "":
    return ""
  try:
    amount = float(value)
  except (TypeError, ValueError):
    return clean_text(value)
  if amount >= 10000:
    return f"{amount / 10000:.1f}억원"
  return f"{int(amount):,}만원"


def format_percent(value: Any) -> str:
  if value is None or value == "":
    return ""
  try:
    return f"{float(value):.2f}%"
  except (TypeError, ValueError):
    return clean_text(value)


def format_number(value: Any) -> str:
  if value is None or value == "":
    return ""
  try:
    number = float(value)
  except (TypeError, ValueError):
    return clean_text(value)
  if number.is_integer():
    return f"{int(number):,}"
  return f"{number:,.2f}"


def dedupe(values: list[str]) -> list[str]:
  seen = set()
  result = []
  for value in values:
    if value in seen:
      continue
    seen.add(value)
    result.append(value)
  return result
