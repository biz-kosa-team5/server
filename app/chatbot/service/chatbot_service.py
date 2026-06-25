from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from .agent import (
  ChatbotAgent,
  agent_execution_failed_result,
  agent_initialization_failed_result,
)
from .splitter import split_question


logger = logging.getLogger(__name__)


async def handle_chatbot_query(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
  question = str(payload.get("question", "")).strip()
  agent_initialization_failed = False
  try:
    agent = ChatbotAgent(session)
  except Exception:
    logger.exception("Failed to initialize chatbot agent")
    agent = None
    agent_initialization_failed = True
  fragments = []
  for index, fragment in enumerate(split_question(question) or [question]):
    fragments.append(await handle_fragment(
      agent,
      index,
      fragment,
      agent_initialization_failed=agent_initialization_failed,
    ))
  results = [fragment["result"] for fragment in fragments]
  success = any(result.get("success") is True for result in results)

  return {
    "success": success,
    "question": question,
    "fragments": fragments,
    "result": results[0] if len(results) == 1 else results,
    "message": "질문을 처리했습니다." if success else "처리할 수 있는 질문이 없습니다.",
  }


async def handle_fragment(
  agent: ChatbotAgent | None,
  index: int,
  text: str,
  *,
  agent_initialization_failed: bool = False,
) -> dict[str, Any]:
  try:
    if agent is None:
      result = (
        agent_initialization_failed_result()
        if agent_initialization_failed
        else agent_execution_failed_result()
      )
    else:
      result = await agent.run(text)
  except Exception:
    logger.exception("Failed to run chatbot agent for fragment %s", index)
    result = agent_execution_failed_result()

  return {
    "index": index,
    "text": text,
    "status": "handled" if result.get("success") is True else "not_handled",
    "result": result,
  }
