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
from typing import Any

from openai import OpenAI

from .context import ChatbotAnswerContext, build_llm_context
from .fallback import fallback_answer
from .prompt import CHATBOT_ANSWER_SYSTEM_PROMPT, DEFAULT_ANSWER_MODEL

logger = logging.getLogger(__name__)


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
      return context.message or fallback_answer(context)
    if direct_answer := direct_single_result_answer(context):
      return direct_answer
    if not os.getenv("OPENAI_API_KEY"):
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
              "rawResponse는 원본 응답이고, successfulFragments와 failedFragments는 답변 조립을 위한 정리본이야.\n"
              f"{json.dumps(build_llm_context(context), ensure_ascii=False, indent=2, default=str)}"
            ),
          },
        ],
      )
    except Exception:
      logger.exception("Failed to compose chatbot answer")
      return fallback_answer(context)

    answer = extract_response_content(response)
    return answer or fallback_answer(context)


def normalize_openai_model(model: str) -> str:
  model = model.strip()
  if model.startswith("openai:"):
    model = model.split(":", 1)[1]
  return model or DEFAULT_ANSWER_MODEL


def direct_single_result_answer(context: ChatbotAnswerContext) -> str:
  if context.status != "success" or not isinstance(context.result, dict):
    return ""
  answer = context.result.get("answer")
  if not isinstance(answer, str):
    return ""
  return answer.strip()


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
