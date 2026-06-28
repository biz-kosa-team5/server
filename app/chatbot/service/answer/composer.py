"""
수집된 fragment/tool JSON을 근거로 최상위 answer 문자열을 생성합니다.
전체 실패, API 키 없음, LLM 예외, 빈 응답에서는 도메인 fallback으로 내려가며 새 부동산 사실은 만들지 않습니다.
동기 OpenAI SDK 호출은 이벤트 루프를 막지 않도록 별도 thread에서 실행합니다.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

from openai import OpenAI

from .context import ChatbotAnswerContext
from .fallback import fallback_answer
from .observations import build_answer_observations
from .prompt import CHATBOT_ANSWER_SYSTEM_PROMPT, DEFAULT_ANSWER_MODEL

logger = logging.getLogger(__name__)

DEFAULT_LLM_FAILURE_COOLDOWN_SECONDS = 300.0
_ANSWER_LLM_DISABLED_UNTIL = 0.0


class ChatbotAnswerComposer:
  def __init__(
    self,
    model: str | None = None,
    client: Any | None = None,
  ):
    self.model = normalize_openai_model(
      model or os.getenv("OPENAI_CHAT_MODEL") or DEFAULT_ANSWER_MODEL,
    )
    self._client = client

  async def compose(self, context: ChatbotAnswerContext) -> str:
    if context.success is False:
      return fallback_answer(context)
    if not os.getenv("OPENAI_API_KEY"):
      return fallback_answer(context)
    if answer_llm_temporarily_disabled():
      return fallback_answer(context)

    try:
      client = self._client or OpenAI(api_key=os.environ["OPENAI_API_KEY"])
      response = await asyncio.to_thread(
        client.chat.completions.create,
        model=self.model,
        temperature=0.2,
        messages=[
          {
            "role": "system",
            "content": CHATBOT_ANSWER_SYSTEM_PROMPT,
          },
          {
            "role": "user",
            "content": (
              "아래 JSON 데이터만 근거로 사용자 질문에 답변해줘.\n"
              "rawResponse는 nested answer를 제거하고 축약한 응답이고, successfulObservations와 failedObservations는 답변 조립을 위한 정리본이야.\n"
              f"{json.dumps(build_answer_observations(context), ensure_ascii=False, indent=2, default=str)}"
            ),
          },
        ],
      )
    except Exception as exc:
      if should_cooldown_answer_llm(exc):
        disable_answer_llm_temporarily()
      logger.exception("Failed to compose chatbot answer")
      return fallback_answer(context)

    answer = extract_response_content(response)
    return answer or fallback_answer(context)


def normalize_openai_model(model: str) -> str:
  model = model.strip()
  if model.startswith("openai:"):
    model = model.split(":", 1)[1]
  return model or DEFAULT_ANSWER_MODEL


def answer_llm_temporarily_disabled() -> bool:
  return time.monotonic() < _ANSWER_LLM_DISABLED_UNTIL


def disable_answer_llm_temporarily() -> None:
  global _ANSWER_LLM_DISABLED_UNTIL
  _ANSWER_LLM_DISABLED_UNTIL = time.monotonic() + answer_llm_failure_cooldown_seconds()


def answer_llm_failure_cooldown_seconds() -> float:
  value = os.getenv("CHATBOT_ANSWER_LLM_FAILURE_COOLDOWN_SECONDS")
  if value is None:
    return DEFAULT_LLM_FAILURE_COOLDOWN_SECONDS
  try:
    cooldown = float(value)
  except ValueError:
    return DEFAULT_LLM_FAILURE_COOLDOWN_SECONDS
  return max(0.0, cooldown)


def should_cooldown_answer_llm(exc: Exception) -> bool:
  status_code = getattr(exc, "status_code", None)
  if status_code == 429:
    return True
  error_code = getattr(exc, "code", None)
  if error_code == "insufficient_quota":
    return True
  return exc.__class__.__name__ == "RateLimitError"


def extract_response_content(response: Any) -> str:
  choices = get_value(response, "choices")
  if not choices:
    return ""

  first_choice = choices[0]
  message = get_value(first_choice, "message")
  content = get_value(message, "content")
  if not isinstance(content, str):
    return ""
  return content.strip()


def get_value(value: Any, key: str) -> Any:
  if isinstance(value, dict):
    return value.get(key)
  return getattr(value, key, None)
