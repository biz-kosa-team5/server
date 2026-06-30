from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import Callable
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import load_environment
from app.real_estate.support import optional_int

from .formatting import RECOMMENDATION_RESULT_LIMIT


logger = logging.getLogger(__name__)
RecommendationRunner = Callable[[Session, dict[str, Any], str], dict[str, Any]]


def run_recommendation_with_ai_selection(
  session: Session,
  slots: dict[str, Any],
  text: str = "",
  *,
  base_runner: RecommendationRunner | None = None,
) -> dict[str, Any]:
  from .service import run_recommendation

  runner = base_runner or run_recommendation
  if resolve_openai_api_key() is None:
    return runner(session, slots, text)

  internal_slots = dict(slots)
  internal_slots["_include_candidate_pool"] = True
  result = runner(session, internal_slots, text)
  candidate_pool = [item for item in result.get("_candidatePool", []) if isinstance(item, dict)]
  if result.get("success") is not True or not candidate_pool:
    return strip_private_result(result)

  limit = selection_limit(slots, candidate_pool)
  try:
    selection = select_candidate_ids(candidate_pool, text, limit)
    selected_ids = validate_selected_ids(selection.get("selectedComplexIds"), candidate_pool, limit)
  except Exception:
    logger.exception("AI recommendation selection failed")
    return fallback_result(result, candidate_pool, limit)

  return selected_result(result, candidate_pool, selected_ids, selection, mode="ai")


def select_candidate_ids(candidate_pool: list[dict[str, Any]], question: str, limit: int) -> dict[str, Any]:
  api_key = resolve_openai_api_key()
  if api_key is None:
    raise RuntimeError("missing_openai_api_key")

  client = OpenAI(api_key=api_key)
  request: dict[str, Any] = {
    "model": selector_model(),
    "messages": [
      {
        "role": "system",
        "content": (
          "candidatePool 안의 아파트 중 최종 추천 후보를 고르는 selector입니다. "
          "candidatePool 밖 단지를 만들지 마세요. 서버 hard filter는 이미 적용됐습니다. "
          "가장 싼 후보를 자동 선택하지 말고, 질문 의도에 맞춰 가격, 평형, 세대수, 준공연도, 거래일, "
          "역/학교/생활편의, _caveats를 종합하세요. "
          "일반 추천에서는 100세대 미만, 15평 미만 같은 _caveats가 있는 후보를 낮은 우선순위로 두세요. "
          "사용자가 최저가/소형을 명시하지 않았고 caveat가 적은 대안이 있으면 소단지·초소형 후보를 선택하지 마세요. "
          "생활편의 질문도 생활편의 거리만 보지 말고 주거 후보로서의 균형을 먼저 본 뒤 고르세요. JSON만 반환하세요."
        ),
      },
      {
        "role": "user",
        "content": json.dumps({
          "question": question,
          "selectionLimit": limit,
          "candidatePool": compact_candidates_for_prompt(candidate_pool),
          "requiredOutput": {
            "selectedComplexIds": ["number"],
            "selectionReasons": {"complexId": "짧은 선택 이유"},
            "tradeoffs": {"complexId": "주의할 약점"},
          },
        }, ensure_ascii=False, default=str),
      },
    ],
    "response_format": {"type": "json_object"},
  }
  if not selector_model().startswith("gpt-5"):
    request["temperature"] = 0.1
  response = client.chat.completions.create(**request)
  content = response.choices[0].message.content if response.choices else ""
  return json.loads(content or "{}")


def validate_selected_ids(raw_ids: Any, candidate_pool: list[dict[str, Any]], limit: int) -> list[int]:
  if not isinstance(raw_ids, list):
    raise ValueError("selectedComplexIds must be a list")
  selected_ids = [int(item) for item in raw_ids]
  expected_count = min(limit, len(candidate_pool))
  if len(selected_ids) != expected_count:
    raise ValueError("invalid selection count")
  if len(set(selected_ids)) != len(selected_ids):
    raise ValueError("duplicated selection id")
  candidate_ids = {
    int(item["complexId"])
    for item in candidate_pool
    if item.get("complexId") is not None
  }
  if any(item not in candidate_ids for item in selected_ids):
    raise ValueError("selection outside candidatePool")
  return selected_ids


def selected_result(
  result: dict[str, Any],
  candidate_pool: list[dict[str, Any]],
  selected_ids: list[int],
  selection: dict[str, Any],
  *,
  mode: str,
) -> dict[str, Any]:
  by_id = {
    int(item["complexId"]): item
    for item in candidate_pool
    if item.get("complexId") is not None
  }
  reasons = selection.get("selectionReasons") if isinstance(selection.get("selectionReasons"), dict) else {}
  tradeoffs = selection.get("tradeoffs") if isinstance(selection.get("tradeoffs"), dict) else {}
  rows = []
  for complex_id in selected_ids:
    row = strip_private_result(dict(by_id[complex_id]))
    reason = reasons.get(str(complex_id)) or reasons.get(complex_id)
    tradeoff = tradeoffs.get(str(complex_id)) or tradeoffs.get(complex_id)
    if isinstance(reason, str) and reason.strip():
      row["recommendationReason"] = reason.strip()
    if isinstance(tradeoff, str) and tradeoff.strip():
      row["selectionTradeoff"] = tradeoff.strip()
    rows.append(row)

  public = strip_private_result(result)
  public["results"] = rows
  public["success"] = bool(rows)
  public["selection"] = {
    "mode": mode,
    "candidatePoolSize": len(candidate_pool),
    "selectedComplexIds": selected_ids,
  }
  return public


def fallback_result(result: dict[str, Any], candidate_pool: list[dict[str, Any]], limit: int) -> dict[str, Any]:
  public = strip_private_result(result)
  public["selection"] = {
    "mode": "fallback",
    "candidatePoolSize": len(candidate_pool),
    "selectedComplexIds": [
      item.get("complexId")
      for item in public.get("results", [])[:limit]
      if isinstance(item, dict)
    ],
  }
  return public


def strip_private_result(value: Any) -> Any:
  if isinstance(value, list):
    return [strip_private_result(item) for item in value]
  if isinstance(value, dict):
    return {
      key: strip_private_result(item)
      for key, item in value.items()
      if not str(key).startswith("_")
    }
  return value


def compact_candidates_for_prompt(candidate_pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
  compacted = []
  for item in candidate_pool:
    infrastructure = item.get("infrastructure") if isinstance(item.get("infrastructure"), dict) else {}
    compacted.append({
      "complexId": item.get("complexId"),
      "complexName": item.get("complexName"),
      "address": item.get("address"),
      "latestDealAmountText": item.get("latestDealAmountText"),
      "latestDealDate": item.get("latestDealDate"),
      "pyeong": item.get("pyeong"),
      "unitCnt": item.get("unitCnt"),
      "useDate": item.get("useDate"),
      "matchedPois": item.get("matchedPois", []),
      "nearestStation": infrastructure.get("nearestStation"),
      "nearestEducation": infrastructure.get("nearestEducation"),
      "nearbyLifestyle": infrastructure.get("nearbyLifestyle", [])[:4]
      if isinstance(infrastructure.get("nearbyLifestyle"), list)
      else [],
      "_caveats": item.get("_caveats", []),
    })
  return compacted


def selection_limit(slots: dict[str, Any], candidate_pool: list[dict[str, Any]]) -> int:
  requested_limit = optional_int(slots.get("limit"))
  limit = min(max(requested_limit or RECOMMENDATION_RESULT_LIMIT, 1), RECOMMENDATION_RESULT_LIMIT)
  return min(limit, len(candidate_pool))


def resolve_openai_api_key() -> str | None:
  if "pytest" in sys.modules:
    return None
  load_environment()
  key = os.getenv("OPENAI_API_KEY", "").strip()
  return key or None


def selector_model() -> str:
  model = os.getenv("OPENAI_RECOMMENDATION_SELECTOR_MODEL") or os.getenv("OPENAI_CHAT_MODEL") or "gpt-4o-mini"
  model = model.strip()
  if model.startswith("openai:"):
    model = model.split(":", 1)[1]
  return model or "gpt-4o-mini"
