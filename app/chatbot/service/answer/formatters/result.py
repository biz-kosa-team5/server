"""
tool 결과 JSON을 최종 fallback 문장으로 라우팅합니다.
feature 단계 answer는 재사용하지 않고 handler observation을 formatter로 요약합니다.
"""
from __future__ import annotations

from typing import Any

from .common import clean_text, collect_result_messages, format_failure_reason
from .comparison import format_comparison_result
from .legal_contract import format_legal_contract_result
from .price_trend import format_price_trend_result
from .recommendation import format_recommendation_result
from .simple_lookup import format_simple_lookup_result


def format_result_messages(result: Any) -> list[str]:
  if isinstance(result, list):
    messages = []
    for item in result:
      messages.extend(format_result_messages(item))
    return messages

  if not isinstance(result, dict):
    return []

  if is_specialist_wrapper(result):
    nested_messages = format_result_messages(result.get("result"))
    if nested_messages:
      return nested_messages

  domain_message = format_domain_result(result)
  if domain_message:
    return [domain_message]

  if result.get("success") is False:
    nested_result = result.get("result")
    nested_messages = format_result_messages(nested_result)
    if nested_messages:
      return nested_messages
    reason = format_failure_reason(result)
    return [reason] if reason else []

  nested_result = result.get("result")
  nested_messages = format_result_messages(nested_result)
  if nested_messages:
    return nested_messages

  nested_results = result.get("results")
  nested_result_messages = format_result_messages(nested_results)
  if nested_result_messages:
    return nested_result_messages

  return collect_result_messages(result)


def format_domain_result(result: dict[str, Any]) -> str:
  handler = clean_text(result.get("handler"))
  if handler == "simple_lookup":
    return format_simple_lookup_result(result)
  if handler == "price_trend":
    return format_price_trend_result(result)
  if handler == "recommendation":
    return format_recommendation_result(result)
  if handler == "comparison":
    return format_comparison_result(result)
  if handler == "legal_contract":
    return format_legal_contract_result(result)
  return ""


def is_specialist_wrapper(result: dict[str, Any]) -> bool:
  return "agent" in result and isinstance(result.get("result"), (dict, list))
