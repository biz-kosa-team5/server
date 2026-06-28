"""
LLM을 사용할 수 없을 때 tool JSON만으로 결정적인 한국어 fallback 답변을 만듭니다.
부분 성공은 성공 fragment를 먼저 요약하고 실패 fragment의 message/reason만 짧게 덧붙입니다.
"""
from __future__ import annotations

from typing import Any

from .context import ChatbotAnswerContext
from .formatters import (
  clean_text,
  collect_result_messages,
  dedupe,
  first_non_empty,
  format_failure_reason,
  format_result_messages,
)


def fallback_answer(context: ChatbotAnswerContext) -> str:
  status_message = context.message.strip()
  if context.success is False:
    result_messages = dedupe([
      *format_result_messages(context.result),
      *collect_result_messages(context.result),
    ])
    return first_non_empty([*result_messages, status_message, "처리할 수 있는 질문이 없습니다."])

  if context.status == "partial_success":
    messages = dedupe([
      *collect_successful_fragment_messages(context.fragments),
      *collect_failed_fragment_messages(context.fragments),
    ])
    if messages:
      return "\n".join(messages)
    return status_message or "일부 질문만 처리했습니다."

  result_messages = dedupe(format_result_messages(context.result))
  if len(result_messages) == 1:
    return result_messages[0]
  if result_messages:
    return "\n".join(f"{index}. {message}" for index, message in enumerate(result_messages, start=1))
  return status_message or "질문을 처리했습니다."


def collect_successful_fragment_messages(fragments: list[dict[str, Any]]) -> list[str]:
  messages = []
  for fragment in fragments:
    if fragment.get("status") != "handled":
      continue
    result = fragment.get("result")
    messages.extend(format_result_messages(result))
  return messages


def collect_failed_fragment_messages(fragments: list[dict[str, Any]]) -> list[str]:
  messages = []
  for fragment in fragments:
    if fragment.get("status") == "handled":
      continue
    text = clean_text(fragment.get("text"))
    result = fragment.get("result")
    result_messages = format_result_messages(result)
    if result_messages:
      if is_domain_result(result):
        messages.extend(result_messages)
      elif text and len(result_messages) == 1:
        messages.append(f"{text}는 처리하지 못했습니다. {result_messages[0]}")
      else:
        messages.extend(result_messages)
      continue
    reason = format_failure_reason(result)
    if text and reason:
      messages.append(f"{text}는 처리하지 못했습니다. {reason}")
    elif text:
      messages.append(f"{text}는 처리하지 못했습니다.")
    elif reason:
      messages.append(reason)
  return messages


def is_domain_result(result: Any) -> bool:
  return isinstance(result, dict) and bool(result.get("handler") or result.get("agent"))
