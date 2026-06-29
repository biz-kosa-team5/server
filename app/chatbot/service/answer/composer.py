"""
수집된 fragment/tool JSON을 근거로 최상위 answer 문자열을 생성합니다.
전체 실패, LLM 호출 불가/예외, 빈 응답에서는 도메인 fallback으로 내려가며 새 부동산 사실은 만들지 않습니다.
동기 OpenAI SDK 호출은 이벤트 루프를 막지 않도록 별도 thread에서 실행합니다.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any

from openai import OpenAI

from app.config import load_environment

from .context import ChatbotAnswerContext
from .fallback import fallback_answer
from .observations import build_answer_observations
from .prompt import CHATBOT_ANSWER_SYSTEM_PROMPT, DEFAULT_ANSWER_MODEL

logger = logging.getLogger(__name__)

DEFAULT_LLM_FAILURE_COOLDOWN_SECONDS = 300.0
_ANSWER_LLM_DISABLED_UNTIL = 0.0
MAX_FINAL_ANSWER_LENGTH = 500
FORBIDDEN_ANSWER_TERMS = (
  "handler",
  "agent",
  "tool",
  "execution",
  "planType",
  "dedupe",
  "fragment",
)
COORDINATE_PATTERNS = (
  re.compile(
    r"좌표는?\s*위도\s*[-+]?\d+(?:\.\d+)?\s*,?\s*경도\s*[-+]?\d+(?:\.\d+)?(?:입니다\.?|[.!?。])?",
    re.IGNORECASE,
  ),
  re.compile(
    r"위도\s*[-+]?\d+(?:\.\d+)?\s*,?\s*경도\s*[-+]?\d+(?:\.\d+)?(?:입니다\.?|[.!?。])?",
    re.IGNORECASE,
  ),
  re.compile(r"latitude\s*[:=]?\s*[-+]?\d+(?:\.\d+)?\s*,?\s*longitude\s*[:=]?\s*[-+]?\d+(?:\.\d+)?", re.IGNORECASE),
  re.compile(r"longitude\s*[:=]?\s*[-+]?\d+(?:\.\d+)?\s*,?\s*latitude\s*[:=]?\s*[-+]?\d+(?:\.\d+)?", re.IGNORECASE),
)


class ChatbotAnswerComposer:
  def __init__(
    self,
    model: str | None = None,
    client: Any | None = None,
    api_key: str | None = None,
  ):
    self.model = normalize_openai_model(
      model or os.getenv("OPENAI_CHAT_MODEL") or DEFAULT_ANSWER_MODEL,
    )
    self._client = client
    self._api_key = api_key

  async def compose(self, context: ChatbotAnswerContext) -> str:
    if context.success is False:
      return finalize_answer_text(fallback_answer(context), context)
    if answer_llm_temporarily_disabled():
      return finalize_answer_text(fallback_answer(context), context)

    client = self._client or openai_client(self._api_key)
    if client is None:
      return finalize_answer_text(fallback_answer(context), context)

    try:
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
      return finalize_answer_text(fallback_answer(context), context)

    answer = extract_response_content(response)
    return finalize_answer_text(answer or fallback_answer(context), context)


def openai_client(api_key: str | None = None) -> OpenAI | None:
  resolved_key = resolve_openai_api_key(api_key)
  if not resolved_key:
    return None
  return OpenAI(api_key=resolved_key)


def resolve_openai_api_key(api_key: str | None = None) -> str | None:
  if api_key and api_key.strip():
    return api_key.strip()
  load_environment()
  resolved_key = os.getenv("OPENAI_API_KEY", "").strip()
  return resolved_key or None


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


def finalize_answer_text(answer: str, context: ChatbotAnswerContext) -> str:
  text = normalize_answer_whitespace(answer)
  text = remove_coordinate_text(text)
  if has_forbidden_answer_terms(text):
    fallback = remove_coordinate_text(normalize_answer_whitespace(fallback_answer(context)))
    if has_forbidden_answer_terms(fallback):
      fallback = remove_forbidden_sentences(fallback)
    text = fallback
  text = truncate_answer(text)
  return text or context.message or "질문을 처리했습니다."


def normalize_answer_whitespace(answer: str) -> str:
  text = str(answer or "").replace("\r\n", "\n").replace("\r", "\n").strip()
  text = re.sub(r"\n{3,}", "\n\n", text)
  text = re.sub(r"[ \t]+", " ", text)
  return text


def remove_coordinate_text(answer: str) -> str:
  text = answer
  for pattern in COORDINATE_PATTERNS:
    text = pattern.sub("", text)
  return normalize_answer_whitespace(text)


def has_forbidden_answer_terms(answer: str) -> bool:
  lowered = answer.lower()
  return any(term.lower() in lowered for term in FORBIDDEN_ANSWER_TERMS)


def remove_forbidden_sentences(answer: str) -> str:
  sentences = split_sentences(answer)
  kept = [
    sentence
    for sentence in sentences
    if not has_forbidden_answer_terms(sentence)
  ]
  return normalize_answer_whitespace(" ".join(kept))


def truncate_answer(answer: str) -> str:
  if len(answer) <= MAX_FINAL_ANSWER_LENGTH:
    return answer

  sentences = split_sentences(answer)
  kept = []
  current_length = 0
  for sentence in sentences:
    next_length = current_length + len(sentence) + (1 if kept else 0)
    if next_length > MAX_FINAL_ANSWER_LENGTH:
      break
    kept.append(sentence)
    current_length = next_length
  if kept:
    return normalize_answer_whitespace(" ".join(kept))
  return answer[: MAX_FINAL_ANSWER_LENGTH - 3].rstrip() + "..."


def split_sentences(answer: str) -> list[str]:
  sentences = re.findall(r"[^.!?\n。]+[.!?。]?", answer)
  return [sentence.strip() for sentence in sentences if sentence.strip()]


def get_value(value: Any, key: str) -> Any:
  if isinstance(value, dict):
    return value.get(key)
  return getattr(value, key, None)
