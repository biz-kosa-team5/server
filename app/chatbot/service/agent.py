from __future__ import annotations

import ast
import json
import os
from typing import Any

from langchain.agents import create_agent
from sqlalchemy.orm import Session

from .tools import build_chatbot_tools


DEFAULT_AGENT_MODEL = "openai:gpt-4o-mini"

CHATBOT_AGENT_SYSTEM_PROMPT = """
당신은 강남 3구 부동산과 부동산 계약 법령 질문을 처리하는 챗봇 Agent입니다.

반드시 지켜야 할 규칙:
- 사용자의 질문이 부동산 단지 조회, 아파트 추천, 단지 비교, 시세 추이, 계약 관련 법령 질문이면 제공된 tool 중 하나를 호출하세요.
- tool 호출 없이 추측으로 답하지 마세요.
- tool 인자는 가능한 한 구조화해서 채우세요. 모르는 값은 생략하세요.
- 가격 단위는 만원입니다. 예: 40억은 400000입니다.
- 질문이 지원 범위 밖이면 tool을 호출하지 않아도 됩니다.
""".strip()


class ChatbotAgent:
  def __init__(self, session: Session, model: str | None = None):
    self.agent = create_agent(
      model=model or os.getenv("OPENAI_CHAT_MODEL", DEFAULT_AGENT_MODEL),
      tools=build_chatbot_tools(session),
      system_prompt=CHATBOT_AGENT_SYSTEM_PROMPT,
    )

  async def run(self, question: str) -> dict[str, Any]:
    result = await self.agent.ainvoke({
      "messages": [{"role": "user", "content": question}],
    })
    return extract_agent_result(result)


def extract_agent_result(result: dict[str, Any]) -> dict[str, Any]:
  tool_results = [
    parsed
    for parsed in (
      parse_tool_message(message)
      for message in result.get("messages", [])
    )
    if parsed is not None
  ]

  if not tool_results:
    return no_matching_tool_result()
  if len(tool_results) == 1:
    return tool_results[0]
  return {
    "success": any(item.get("success") is True for item in tool_results),
    "results": tool_results,
  }


def parse_tool_message(message: Any) -> dict[str, Any] | None:
  if getattr(message, "type", None) != "tool":
    return None

  content = getattr(message, "content", None)
  if isinstance(content, dict):
    return content
  if isinstance(content, list):
    return parse_tool_content_list(content)
  if isinstance(content, str):
    return parse_tool_content_text(content)
  return None


def parse_tool_content_list(content: list[Any]) -> dict[str, Any] | None:
  for item in content:
    if isinstance(item, dict) and isinstance(item.get("text"), str):
      parsed = parse_tool_content_text(item["text"])
      if parsed is not None:
        return parsed
    if isinstance(item, dict) and item.get("type") == "json":
      value = item.get("json")
      if isinstance(value, dict):
        return value
  return None


def parse_tool_content_text(content: str) -> dict[str, Any] | None:
  text = content.strip()
  if not text:
    return None
  for parser in (json.loads, ast.literal_eval):
    try:
      parsed = parser(text)
    except (SyntaxError, ValueError, TypeError, json.JSONDecodeError):
      continue
    if isinstance(parsed, dict):
      return parsed
  return None


def no_matching_tool_result() -> dict[str, Any]:
  return {
    "success": False,
    "reason": "no_matching_tool",
    "message": "현재 챗봇은 부동산 단지 조회, 아파트 추천, 단지 비교, 시세 추이, 계약 관련 법령 질문을 처리할 수 있습니다.",
  }


def agent_execution_failed_result() -> dict[str, Any]:
  return {
    "success": False,
    "reason": "agent_execution_failed",
    "message": "Agent 실행 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
  }
