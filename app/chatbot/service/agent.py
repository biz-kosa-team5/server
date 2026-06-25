from __future__ import annotations

import ast
import json
import os
from typing import Any

from langchain.agents import create_agent
from sqlalchemy.orm import Session

from .tools import build_chatbot_tools


DEFAULT_AGENT_MODEL = "openai:gpt-4o-mini"

SUPPORTED_QUESTION_EXAMPLES = [
  "잠실엘스 위치 알려줘",
  "송파구 30억 이하 아파트 추천해줘",
  "래미안대치팰리스랑 잠실엘스 가격 비교해줘",
  "최근 1년 잠실엘스 시세 추이 알려줘",
  "매매 계약금 해제 규정 알려줘",
]

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
  tool_messages = [
    message
    for message in result.get("messages", [])
    if getattr(message, "type", None) == "tool"
  ]
  tool_results = [
    parsed
    for parsed in (
      parse_tool_message(message)
      for message in tool_messages
    )
    if parsed is not None
  ]

  if not tool_messages:
    return no_matching_tool_result()
  if not tool_results:
    return tool_result_parse_failed_result()
  if len(tool_messages) == 1:
    return tool_results[0]
  return aggregate_tool_results(tool_messages, tool_results)


def aggregate_tool_results(tool_messages: list[Any], tool_results: list[dict[str, Any]]) -> dict[str, Any]:
  total = len(tool_messages)
  succeeded = sum(1 for item in tool_results if item.get("success") is True)
  failed = total - succeeded

  if succeeded == total:
    return {
      "success": True,
      "status": "success",
      "message": "여러 조회 결과를 처리했습니다.",
      "results": tool_results,
      "executionSummary": execution_summary(total, succeeded, failed),
    }
  if succeeded > 0:
    return {
      "success": True,
      "status": "partial_success",
      "message": "일부 조회 결과만 처리했습니다.",
      "results": tool_results,
      "executionSummary": execution_summary(total, succeeded, failed),
    }
  return {
    "success": False,
    "status": "failed",
    "reason": "all_tool_results_failed",
    "message": "조회 결과를 처리하지 못했습니다.",
    "results": tool_results,
    "executionSummary": execution_summary(total, succeeded, failed),
  }


def execution_summary(total: int, succeeded: int, failed: int) -> dict[str, int]:
  return {
    "total": total,
    "succeeded": succeeded,
    "failed": failed,
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
    "message": "지원 가능한 질문은 단지 조회, 아파트 추천, 단지 비교, 시세 추이, 계약 법령 질문입니다.",
    "suggestedQuestions": SUPPORTED_QUESTION_EXAMPLES,
  }


def tool_result_parse_failed_result() -> dict[str, Any]:
  return {
    "success": False,
    "reason": "tool_result_parse_failed",
    "message": "조회 결과를 해석하지 못했습니다. 잠시 후 다시 시도해 주세요.",
  }


def agent_execution_failed_result() -> dict[str, Any]:
  return {
    "success": False,
    "reason": "agent_execution_failed",
    "message": "질문 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
  }


def agent_initialization_failed_result() -> dict[str, Any]:
  return {
    "success": False,
    "reason": "agent_initialization_failed",
    "message": "챗봇 실행 준비 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
  }
