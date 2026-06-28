from __future__ import annotations

import re
from typing import Any


def dedupe_specialist_results(items: list[Any]) -> tuple[list[Any], int]:
  return dedupe_items(items)


def dedupe_tool_results(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
  deduped, count = dedupe_items(items)
  return deduped, count


def dedupe_items(items: list[Any]) -> tuple[list[Any], int]:
  deduped = []
  seen = set()
  for item in items:
    signature = result_signature(item)
    if signature in seen:
      continue
    seen.add(signature)
    deduped.append(item)
  return deduped, len(items) - len(deduped)


def result_signature(item: Any) -> tuple[Any, ...]:
  result = unwrap_result(item)
  if not isinstance(result, dict):
    return ("raw", canonicalize(result))

  handler = result.get("handler")
  if handler == "simple_lookup":
    criteria = dict_value(result.get("criteria"))
    return (
      "simple_lookup",
      value(result, criteria, "query_type"),
      value(result, criteria, "target_name"),
      criteria.get("complex_name"),
      value(result, criteria, "period"),
      value(result, criteria, "limit"),
    )

  if handler == "price_trend":
    criteria = dict_value(result.get("criteria"))
    return (
      "price_trend",
      value(result, criteria, "analysis_type") or result.get("observation_type"),
      value(result, criteria, "target_type"),
      value(result, criteria, "target_name"),
      value(result, criteria, "start_date"),
      value(result, criteria, "end_date"),
      value(result, criteria, "period"),
      value(result, criteria, "interval"),
      value(result, criteria, "direction"),
      value(result, criteria, "limit"),
    )

  if handler == "recommendation":
    return (
      "recommendation",
      canonicalize(dict_value(result.get("criteria"))),
    )

  if handler == "comparison":
    criteria = dict_value(result.get("criteria"))
    return (
      "comparison",
      tuple(sorted(str(name) for name in list_value(criteria.get("apartment_names")))),
      tuple(sorted(str(metric) for metric in list_value(criteria.get("metrics")))),
    )

  if handler == "legal_contract":
    return (
      "legal_contract",
      normalize_question(result.get("question")),
    )

  if "result" in result:
    return result_signature(result.get("result"))

  return (
    "generic",
    result.get("agent"),
    result.get("reason"),
    result.get("message"),
    canonicalize(result),
  )


def unwrap_result(item: Any) -> Any:
  if isinstance(item, dict):
    if "result" in item and "agent" in item:
      return item.get("result")
    return item
  result = getattr(item, "result", None)
  if result is not None:
    return result
  return item


def value(result: dict[str, Any], criteria: dict[str, Any], key: str) -> Any:
  return result.get(key) if result.get(key) is not None else criteria.get(key)


def dict_value(value: Any) -> dict[str, Any]:
  return value if isinstance(value, dict) else {}


def list_value(value: Any) -> list[Any]:
  return value if isinstance(value, list) else []


def normalize_question(value: Any) -> str:
  return re.sub(r"\s+", " ", str(value or "").strip().lower())


def canonicalize(value: Any) -> Any:
  if isinstance(value, dict):
    return tuple(
      (key, canonicalize(item))
      for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
      if key != "answer"
    )
  if isinstance(value, list):
    return tuple(canonicalize(item) for item in value)
  if isinstance(value, set):
    return tuple(sorted(canonicalize(item) for item in value))
  return value
