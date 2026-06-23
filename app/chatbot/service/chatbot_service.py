from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .agent import ChatbotAgent, agent_execution_failed_result
from .splitter import split_question


async def handle_chatbot_query(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
  question = str(payload.get("question", "")).strip()
  try:
    agent = ChatbotAgent(session)
  except Exception:
    agent = None
  fragments = []
  for index, fragment in enumerate(split_question(question) or [question]):
    fragments.append(await handle_fragment(agent, index, fragment))
  results = [fragment["result"] for fragment in fragments]
  success = any(result.get("success") is True for result in results)

  return {
    "success": success,
    "question": question,
    "fragments": fragments,
    "result": results[0] if len(results) == 1 else results,
    "message": "질문을 처리했습니다." if success else "처리할 수 있는 질문이 없습니다.",
  }


async def handle_fragment(agent: ChatbotAgent | None, index: int, text: str) -> dict[str, Any]:
  try:
    result = agent_execution_failed_result() if agent is None else await agent.run(text)
  except Exception:
    result = agent_execution_failed_result()

  return {
    "index": index,
    "text": text,
    "status": "handled" if result.get("success") is True else "not_handled",
    "result": result,
  }
