"""
tool 결과 JSON을 최종 fallback 문장으로 라우팅합니다.
feature 단계에서 만든 answer를 우선 사용하고, 별도 answer가 없는 simple_lookup/price_trend만 formatter로 요약합니다.
"""
from __future__ import annotations

from typing import Any

from .common import clean_text, collect_result_messages, format_failure_reason
from .price_trend import format_price_trend_result
from .simple_lookup import format_simple_lookup_result


def format_result_messages(result: Any) -> list[str]:
  if isinstance(result, list):
    messages = []
    for item in result:
      messages.extend(format_result_messages(item))
    return messages

  if not isinstance(result, dict):
    return []

  if result.get("success") is False:
    nested_result = result.get("result")
    nested_messages = format_result_messages(nested_result)
    if nested_messages:
      return nested_messages
    reason = format_failure_reason(result)
    return [reason] if reason else []

  domain_message = format_domain_result(result)
  if domain_message:
    return [domain_message]

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
  answer = clean_text(result.get("answer"))
  if answer:
    return answer

  handler = clean_text(result.get("handler"))
  if handler == "simple_lookup":
    return format_simple_lookup_result(result)
  if handler == "price_trend":
    return format_price_trend_result(result)
  return ""
