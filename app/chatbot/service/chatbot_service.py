from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.chatbot.features.comparison.service import run_comparison
from app.chatbot.features.comparison.slots import extract_compare_slots
from app.chatbot.features.recommendation.service import run_recommendation
from app.chatbot.features.recommendation.slots import extract_recommendation_slots

from .agent import ChatbotAgent, agent_execution_failed_result
from .splitter import split_question


logger = logging.getLogger(__name__)


async def handle_chatbot_query(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
  question = str(payload.get("question", "")).strip()
  try:
    agent = ChatbotAgent(session)
  except Exception:
    logger.exception("Failed to initialize chatbot agent")
    agent = None
  fragments = []
  for index, fragment in enumerate(split_question(question) or [question]):
    fragments.append(await handle_fragment(session, agent, index, fragment))
  results = [fragment["result"] for fragment in fragments]
  success = any(result.get("success") is True for result in results)

  return {
    "success": success,
    "question": question,
    "fragments": fragments,
    "result": results[0] if len(results) == 1 else results,
    "message": "질문을 처리했습니다." if success else "처리할 수 있는 질문이 없습니다.",
  }


async def handle_fragment(session: Session, agent: ChatbotAgent | None, index: int, text: str) -> dict[str, Any]:
  try:
    result = direct_feature_result(session, text)
    if result is None:
      result = agent_execution_failed_result() if agent is None else await agent.run(text)
  except Exception:
    logger.exception("Failed to handle chatbot fragment")
    result = agent_execution_failed_result()

  return {
    "index": index,
    "text": text,
    "status": "handled" if result.get("success") is True else "not_handled",
    "result": result,
  }


def direct_feature_result(session: Session, text: str) -> dict[str, Any] | None:
  """Route obvious recommendation/comparison questions without an LLM tool hop."""
  if is_comparison_question(text):
    slots = extract_compare_slots(text)
    if len(slots.get("apartment_names", [])) >= 2:
      return run_comparison(session, slots, text)

  if is_recommendation_question(text):
    return run_recommendation(session, extract_recommendation_slots(text), text)

  return None


def is_comparison_question(text: str) -> bool:
  return any(keyword in text for keyword in ("비교", "둘 중", "어디가 더", "차이", " vs ", "VS"))


def is_recommendation_question(text: str) -> bool:
  return any(keyword in text for keyword in ("추천", "권해", "골라", "조건에 맞는"))
