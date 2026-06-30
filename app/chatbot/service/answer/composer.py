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
from .formatters.sequential import format_dependent_recommendation_comparison_answer
from .observations import build_answer_observations
from .prompt import CHATBOT_ANSWER_SYSTEM_PROMPT, DEFAULT_ANSWER_MODEL

logger = logging.getLogger(__name__)

DEFAULT_LLM_FAILURE_COOLDOWN_SECONDS = 300.0
_ANSWER_LLM_DISABLED_UNTIL = 0.0
MAX_FINAL_ANSWER_LENGTH = 1000
MAX_SEQUENCE_ANSWER_LENGTH = 5000
MAX_RECOMMENDATION_ANSWER_LENGTH = 1000
FORBIDDEN_ANSWER_TERMS = (
  "전문 에이전트",
  "handler",
  "agent",
  "tool",
  "execution",
  "planType",
  "dedupe",
  "fragment",
  "raw JSON",
  "latitude",
  "longitude",
  "위도",
  "경도",
  "좌표",
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
    self.last_usage: dict[str, int] | None = None

  async def compose(self, context: ChatbotAnswerContext) -> str:
    # tool 결과가 실패했거나 LLM을 사용할 수 없으면 fallback 답변으로 안전하게 내려간다.
    self.last_usage = None
    sequence_answer = format_dependent_recommendation_comparison_answer(context.result)
    if sequence_answer:
      return finalize_sequence_answer_text(sequence_answer, context)
    if context.success is False:
      return finalize_answer_text(fallback_answer(context), context)
    if answer_llm_temporarily_disabled():
      return finalize_answer_text(fallback_answer(context), context)

    client = self._client or openai_client(self._api_key)
    if client is None:
      return finalize_answer_text(fallback_answer(context), context)

    try:
      request = {
        "model": self.model,
        "messages": [
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
      }
      if supports_custom_temperature(self.model):
        request["temperature"] = 0.2
      response = await asyncio.to_thread(
        client.chat.completions.create,
        **request,
      )
    except Exception as exc:
      if should_cooldown_answer_llm(exc):
        disable_answer_llm_temporarily()
      logger.exception("Failed to compose chatbot answer")
      return finalize_answer_text(fallback_answer(context), context)

    self.last_usage = extract_usage_metadata(response)
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


def supports_custom_temperature(model: str) -> bool:
  return not model.startswith("gpt-5")


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


def extract_usage_metadata(response: Any) -> dict[str, int] | None:
  usage = get_value(response, "usage")
  if usage is None:
    return None

  input_tokens = int_or_zero(get_value(usage, "prompt_tokens") or get_value(usage, "input_tokens"))
  output_tokens = int_or_zero(get_value(usage, "completion_tokens") or get_value(usage, "output_tokens"))
  total_tokens = int_or_zero(get_value(usage, "total_tokens"))
  if total_tokens == 0:
    total_tokens = input_tokens + output_tokens

  cached_tokens = 0
  prompt_details = get_value(usage, "prompt_tokens_details") or get_value(usage, "input_tokens_details")
  if prompt_details is not None:
    cached_tokens = int_or_zero(
      get_value(prompt_details, "cached_tokens")
      or get_value(prompt_details, "cache_read")
    )

  if input_tokens == 0 and output_tokens == 0 and total_tokens == 0:
    return None
  return {
    "input_tokens": input_tokens,
    "output_tokens": output_tokens,
    "cached_tokens": cached_tokens,
    "total_tokens": total_tokens,
  }


def int_or_zero(value: Any) -> int:
  try:
    return int(value)
  except (TypeError, ValueError):
    return 0


def finalize_answer_text(answer: str, context: ChatbotAnswerContext) -> str:
  # 최종 답변에서 내부 용어(handler/tool 등)와 좌표 문장을 제거하고, 추천 답변은 목록형으로 고정한다.
  text = normalize_answer_whitespace(answer)
  text = remove_coordinate_text(text)
  if has_forbidden_answer_terms(text):
    fallback = remove_coordinate_text(normalize_answer_whitespace(fallback_answer(context)))
    if has_forbidden_answer_terms(fallback):
      fallback = remove_forbidden_sentences(fallback)
    text = fallback
  candidate_fallback = candidate_selection_fallback(context)
  if candidate_fallback and should_replace_with_candidate_fallback(text, context):
    return truncate_answer(candidate_fallback)
  if not candidate_fallback and (recommendation_text := readable_recommendation_answer(context)):
    return truncate_answer(recommendation_text, MAX_RECOMMENDATION_ANSWER_LENGTH)
  text = truncate_answer(text)
  text = ensure_required_recommendation_notes(text, context)
  return text or context.message or "질문을 처리했습니다."


def finalize_sequence_answer_text(answer: str, context: ChatbotAnswerContext) -> str:
  text = normalize_answer_whitespace(answer)
  text = remove_coordinate_text(text)
  if has_forbidden_answer_terms(text):
    fallback = remove_coordinate_text(normalize_answer_whitespace(fallback_answer(context)))
    text = remove_forbidden_sentences(fallback) if has_forbidden_answer_terms(fallback) else fallback
  text = truncate_answer(text, MAX_SEQUENCE_ANSWER_LENGTH)
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


def candidate_selection_fallback(context: ChatbotAnswerContext) -> str:
  if not context_has_candidates(context):
    return ""
  fallback = remove_coordinate_text(normalize_answer_whitespace(fallback_answer(context)))
  if has_forbidden_answer_terms(fallback):
    fallback = remove_forbidden_sentences(fallback)
  return fallback


def should_replace_with_candidate_fallback(answer: str, context: ChatbotAnswerContext) -> bool:
  candidates = candidate_rows_from_context(context)
  if not candidates:
    return False
  if is_missing_only_candidate_answer(answer):
    return True
  if context_has_candidate_groups(context) and looks_like_confirmed_comparison(answer):
    return True
  return not enough_candidate_names_in_answer(answer, candidates)


def context_has_candidates(context: ChatbotAnswerContext) -> bool:
  return bool(candidate_rows_from_context(context))


def context_has_candidate_groups(context: ChatbotAnswerContext) -> bool:
  return any(
    isinstance(result, dict)
    and isinstance(result.get("candidateGroups"), list)
    and bool(result.get("candidateGroups"))
    for result in iter_results(context.result)
  )


def candidate_rows_from_context(context: ChatbotAnswerContext) -> list[dict[str, Any]]:
  rows: list[dict[str, Any]] = []
  for result in iter_results(context.result):
    if not isinstance(result, dict):
      continue
    rows.extend([
      item
      for item in result.get("candidates", [])
      if isinstance(item, dict)
    ] if isinstance(result.get("candidates"), list) else [])
    groups = result.get("candidateGroups")
    if isinstance(groups, list):
      for group in groups:
        if not isinstance(group, dict):
          continue
        rows.extend([
          item
          for item in group.get("candidates", [])
          if isinstance(item, dict)
        ] if isinstance(group.get("candidates"), list) else [])
  return rows


def is_missing_only_candidate_answer(answer: str) -> bool:
  if any(token in answer for token in ("여러", "후보", "어느", "선택", "골라")):
    return False
  return any(token in answer for token in ("찾을 수 없습니다", "찾지 못했습니다", "없습니다", "데이터가 부족합니다"))


def looks_like_confirmed_comparison(answer: str) -> bool:
  if any(token in answer for token in ("여러", "후보", "어느", "선택", "골라")):
    return False
  return any(token in answer for token in ("비교하면", "비교 결과", "기준으로 비교", "더 가깝", "더 비싸", "더 저렴"))


def enough_candidate_names_in_answer(answer: str, candidates: list[dict[str, Any]]) -> bool:
  names = dedupe_candidate_names(candidates)
  if not names:
    return True
  required = min(2, len(names))
  mentioned = sum(1 for name in names[:5] if name and name in answer)
  return mentioned >= required


def dedupe_candidate_names(candidates: list[dict[str, Any]]) -> list[str]:
  names = []
  seen = set()
  for candidate in candidates:
    for key in ("complex_name", "complexName", "name", "trade_name", "tradeName"):
      name = str(candidate.get(key) or "").strip()
      if not name or name in seen:
        continue
      seen.add(name)
      names.append(name)
      break
  return names


def truncate_answer(answer: str, max_length: int = MAX_FINAL_ANSWER_LENGTH) -> str:
  if len(answer) <= max_length:
    return answer
  if "\n" in answer:
    return truncate_multiline_answer(answer, max_length)

  sentences = split_sentences(answer)
  kept = []
  current_length = 0
  for sentence in sentences:
    next_length = current_length + len(sentence) + (1 if kept else 0)
    if next_length > max_length:
      break
    kept.append(sentence)
    current_length = next_length
  if kept:
    return normalize_answer_whitespace(" ".join(kept))
  return answer[: max_length - 3].rstrip() + "..."


def truncate_multiline_answer(answer: str, max_length: int) -> str:
  lines = answer.split("\n")
  kept: list[str] = []
  current_length = 0
  for line in lines:
    next_length = current_length + len(line) + (1 if kept else 0)
    if next_length > max_length - 3:
      break
    kept.append(line)
    current_length = next_length
  if kept:
    return "\n".join(kept).rstrip() + "..."
  return answer[: max_length - 3].rstrip() + "..."


def readable_recommendation_answer(context: ChatbotAnswerContext) -> str:
  # 추천 결과는 LLM 문단 그대로 쓰지 않고, 서버에서 번호 목록 형태로 재구성해 가독성을 맞춘다.
  recommendation_results = recommendation_observations(context)
  if not recommendation_results:
    return ""

  result = recommendation_results[0]
  rows = [
    row
    for row in result.get("results", [])
    if isinstance(row, dict)
  ][:5]
  if not rows:
    return ""

  lines = [recommendation_answer_title(result)]
  for index, row in enumerate(rows, start=1):
    name = str(row.get("complexName") or row.get("name") or f"추천 후보 {index}").strip()
    facts = [
      value
      for value in (
        row_station_text(row),
        row_price_text(row),
        row_built_year_text(row),
        row_lifestyle_text(row),
        row_investment_text(row),
        row_redevelopment_text(row),
      )
      if value
    ]
    detail = " · ".join(facts)
    lines.append(f"{index}. {name}" + (f" - {detail}" if detail else ""))

  return normalize_answer_whitespace("\n".join(lines))


def recommendation_answer_title(result: dict[str, Any]) -> str:
  criteria = result.get("criteria")
  if isinstance(criteria, dict):
    if criteria.get("investment_focus") or criteria.get("redevelopment_interest") is True:
      return "투자 참고 신호 기준 추천 후보입니다."
    station_name = str(criteria.get("station_name") or criteria.get("stationName") or "").strip()
    if station_name:
      return f"{station_name} 근처 추천 후보입니다."
  return "조건에 맞는 추천 후보입니다."


def row_station_text(row: dict[str, Any]) -> str:
  matched_pois = row.get("matchedPois")
  if isinstance(matched_pois, list):
    for poi in matched_pois:
      if not isinstance(poi, dict):
        continue
      name = str(poi.get("name") or "").strip()
      distance = format_distance_m(poi.get("distanceM"))
      if name and distance:
        return f"{name} {distance}"

  infrastructure = row.get("infrastructure")
  if not isinstance(infrastructure, dict):
    return ""
  station = infrastructure.get("nearestStation")
  if not isinstance(station, dict):
    return ""
  name = str(station.get("name") or "").strip()
  distance = format_distance_m(station.get("distanceM"))
  if not name or not distance:
    return ""
  return f"{name} {distance}"


def row_price_text(row: dict[str, Any]) -> str:
  price = str(row.get("latestDealAmountText") or row.get("dealAmountText") or "").strip()
  if not price:
    return ""
  return f"최근 거래가 {price}"


def row_built_year_text(row: dict[str, Any]) -> str:
  use_date = str(row.get("useDate") or "").strip()
  if len(use_date) < 4:
    return ""
  year = use_date[:4]
  if not year.isdigit():
    return ""
  return f"{year}년 준공"


def row_lifestyle_text(row: dict[str, Any]) -> str:
  infrastructure = row.get("infrastructure")
  if not isinstance(infrastructure, dict):
    return "생활편의 확인 정보 없음"
  lifestyle = infrastructure.get("nearbyLifestyle")
  if not isinstance(lifestyle, list) or not lifestyle:
    return "생활편의 확인 정보 없음"
  pois = [
    f"{name} {distance}"
    for item in lifestyle
    if isinstance(item, dict)
    if (name := str(item.get("name") or "").strip())
    if (distance := format_distance_m(item.get("distanceM")))
  ][:2]
  if not pois:
    return "생활편의 확인 정보 없음"
  return f"생활편의 {', '.join(pois)}"


def row_redevelopment_text(row: dict[str, Any]) -> str:
  investment_signals = row.get("investmentSignals")
  if isinstance(investment_signals, list) and investment_signals:
    return ""
  redevelopment_info = row.get("redevelopmentInfo")
  if not isinstance(redevelopment_info, list) or not redevelopment_info:
    return "재건축/정비사업 정보 없음"
  first_info = redevelopment_info[0]
  if not isinstance(first_info, dict):
    return "재건축/정비사업 정보 없음"
  title = str(first_info.get("title") or first_info.get("name") or "").strip()
  if not title:
    return "재건축/정비사업 정보 없음"
  return f"재건축/정비사업 {title}"


def row_investment_text(row: dict[str, Any]) -> str:
  investment_signals = row.get("investmentSignals")
  if not isinstance(investment_signals, list) or not investment_signals:
    return ""
  signals = [
    f"{label} {detail}".strip()
    for item in investment_signals
    if isinstance(item, dict)
    if (label := str(item.get("label") or "").strip())
    if (detail := str(item.get("detail") or "").strip())
  ][:2]
  if not signals:
    return ""
  return f"투자 참고 신호 {', '.join(signals)}"


def ensure_required_recommendation_notes(answer: str, context: ChatbotAnswerContext) -> str:
  notes = [
    note
    for note in (
      required_investment_note(context, answer),
      required_lifestyle_note(context, answer),
      required_redevelopment_note(context, answer),
    )
    if note
  ]
  if not notes:
    return answer
  note = " ".join(notes)

  separator = " " if answer else ""
  base_budget = MAX_FINAL_ANSWER_LENGTH - len(separator) - len(note)
  if base_budget <= 0:
    return truncate_answer(note)
  base = truncate_answer(answer, base_budget)
  return normalize_answer_whitespace(f"{base}{separator}{note}")


def required_redevelopment_note(context: ChatbotAnswerContext, answer: str) -> str:
  if mentions_redevelopment(answer):
    return ""
  recommendation_results = recommendation_observations(context)
  if not recommendation_results:
    return ""
  if any(result_has_redevelopment_info(result) for result in recommendation_results):
    return ""
  return "재건축/정비사업은 현재 응답 데이터에서 확인된 정보가 없습니다."


def required_investment_note(context: ChatbotAnswerContext, answer: str) -> str:
  if "투자가치는 예측하지 않고" in answer:
    return ""
  recommendation_results = recommendation_observations(context)
  if not recommendation_results:
    return ""
  for result in recommendation_results:
    criteria = result.get("criteria")
    if isinstance(criteria, dict) and (criteria.get("investment_focus") or criteria.get("redevelopment_interest") is True):
      return "투자가치는 예측하지 않고 확인 가능한 참고 신호 기준입니다."
  return ""


def required_lifestyle_note(context: ChatbotAnswerContext, answer: str) -> str:
  for result in recommendation_observations(context):
    rows = result.get("results")
    if not isinstance(rows, list):
      continue
    for row in rows[:3]:
      if not isinstance(row, dict):
        continue
      infrastructure = row.get("infrastructure")
      if not isinstance(infrastructure, dict):
        continue
      lifestyle = infrastructure.get("nearbyLifestyle")
      if not isinstance(lifestyle, list) or not lifestyle:
        continue
      pois = [
        (name, distance)
        for item in lifestyle
        if isinstance(item, dict)
        if (name := str(item.get("name") or "").strip())
        if (distance := format_distance_m(item.get("distanceM")))
      ][:2]
      if not pois or all(lifestyle_poi_mentioned_with_distance(answer, name, distance) for name, distance in pois):
        continue
      complex_name = str(row.get("complexName") or "첫 후보").strip()
      poi_text = ", ".join(f"{name} {distance}" for name, distance in pois)
      return f"생활편의 거리는 {complex_name} 기준 {poi_text}입니다."
  return ""


def format_distance_m(value: Any) -> str:
  try:
    return f"{round(float(value))}m"
  except (TypeError, ValueError):
    return ""


def lifestyle_poi_mentioned_with_distance(answer: str, name: str, distance: str) -> bool:
  if name not in answer:
    return False
  number = distance.removesuffix("m")
  return distance in answer or f"{number} m" in answer or f"{number}미터" in answer


def recommendation_observations(context: ChatbotAnswerContext) -> list[dict[str, Any]]:
  return [
    result
    for result in iter_results(context.result)
    if isinstance(result, dict)
    and result.get("handler") == "recommendation"
    and result.get("success") is True
    and isinstance(result.get("results"), list)
    and result.get("results")
  ]


def result_has_redevelopment_info(result: dict[str, Any]) -> bool:
  rows = result.get("results")
  if not isinstance(rows, list):
    return False
  return any(
    isinstance(row, dict)
    and isinstance(row.get("redevelopmentInfo"), list)
    and bool(row.get("redevelopmentInfo"))
    for row in rows
  )


def iter_results(value: Any):
  if isinstance(value, list):
    for item in value:
      yield from iter_results(item)
    return
  if not isinstance(value, dict):
    return
  yield value
  nested = value.get("result")
  if nested is not None:
    yield from iter_results(nested)
  nested_results = value.get("results")
  if isinstance(nested_results, list):
    for item in nested_results:
      yield from iter_results(item)


def mentions_redevelopment(answer: str) -> bool:
  return any(keyword in answer for keyword in ("재건축", "재개발", "정비사업"))


def split_sentences(answer: str) -> list[str]:
  sentences = re.findall(r"[^.!?\n。]+[.!?。]?", answer)
  return [sentence.strip() for sentence in sentences if sentence.strip()]


def get_value(value: Any, key: str) -> Any:
  if isinstance(value, dict):
    return value.get(key)
  return getattr(value, key, None)
