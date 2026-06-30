"""
도메인 formatter들이 공유하는 안전한 문자열 변환 유틸입니다.
값이 없거나 타입이 맞지 않는 경우 빈 문자열로 처리해서 fallback 답변이 추측을 섞지 않게 합니다.
"""
from __future__ import annotations

from typing import Any


def format_failure_reason(result: Any) -> str:
  if not isinstance(result, dict):
    return ""
  candidates = list_value(result.get("candidates"))
  if candidates:
    target = result_target_name(result)
    return format_candidate_selection(target, candidates)
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


def format_candidate_selection(
  target_name: str,
  candidates: list[Any],
  *,
  intro: str | None = None,
) -> str:
  rows = [
    dict_value(item)
    for item in candidates[:5]
    if isinstance(item, dict)
  ]
  if not rows:
    return ""

  target = clean_text(target_name) or "입력한 단지명"
  lines = [
    intro or f"{target}로 검색되는 단지가 여러 개 있습니다.",
  ]
  for index, row in enumerate(rows, start=1):
    lines.append(f"{index}. {format_candidate_row(row)}")
  lines.append("어느 단지인지 번호나 동/구를 함께 알려주세요.")
  return "\n".join(lines)


def format_candidate_groups(
  groups: list[Any],
  *,
  resolved_names: list[str] | None = None,
  resolution_notes: list[str] | None = None,
) -> str:
  valid_groups = [
    dict_value(group)
    for group in groups
    if isinstance(group, dict)
  ]
  if not valid_groups:
    return ""

  lines: list[str] = []
  for note in resolution_notes or []:
    note_text = clean_text(note)
    if note_text:
      lines.append(note_text)

  if resolved_names:
    names = ", ".join(name for name in resolved_names if name)
    if names:
      lines.append(f"{names}는 단지로 확인했습니다.")

  for group in valid_groups:
    candidates = list_value(group.get("candidates"))
    target = clean_text(group.get("input")) or "입력한 단지명"
    if candidates:
      lines.append(format_candidate_selection(target, candidates))
      continue
    message = clean_text(group.get("message"))
    if message:
      lines.append(f"{target}: {message}")

  lines.append("비교를 진행하려면 모호한 단지를 먼저 골라주세요.")
  return "\n".join(dedupe(lines))


def format_candidate_row(row: dict[str, Any]) -> str:
  name = candidate_name(row)
  address = clean_text(row.get("address"))
  if address:
    label = address_label(address)
    prefix = f"{label} " if label else ""
    return f"{prefix}{name} - {address}"
  return name or "이름 미상"


def candidate_name(row: dict[str, Any]) -> str:
  return first_non_empty([
    clean_text(row.get("complex_name")),
    clean_text(row.get("complexName")),
    clean_text(row.get("name")),
    clean_text(row.get("trade_name")),
    clean_text(row.get("tradeName")),
  ])


def address_label(address: str) -> str:
  parts = address.split()
  for part in reversed(parts):
    if part.endswith("동") or part.endswith("구"):
      return part
  return parts[-1] if parts else ""


def result_target_name(result: dict[str, Any]) -> str:
  criteria = dict_value(result.get("criteria"))
  slots = dict_value(result.get("slots"))
  return first_non_empty([
    clean_text(criteria.get("target_name")),
    clean_text(criteria.get("complex_name")),
    clean_text(slots.get("target_name")),
  ])
