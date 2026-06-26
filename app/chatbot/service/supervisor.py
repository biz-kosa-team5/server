from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass
import json
import logging
import os
from typing import Any

from langchain.agents import create_agent
from langchain_core.tools import StructuredTool
from sqlalchemy.orm import Session

from .tools import (
  build_comparison_tool,
  build_legal_contract_tool,
  build_price_trend_tool,
  build_recommendation_tool,
  build_simple_lookup_tool,
)


DEFAULT_AGENT_MODEL = "openai:gpt-4o-mini"

logger = logging.getLogger(__name__)

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

SUPERVISOR_AGENT_SYSTEM_PROMPT = """
당신은 강남 3구 부동산 챗봇의 Supervisor Agent입니다.

반드시 지켜야 할 규칙:
- 직접 답변하지 말고, 지원 범위 안의 질문은 반드시 전문 agent tool 중 하나 이상을 호출하세요.
- 하나의 전문 agent로 충분하면 하나만 호출하세요.
- 복합 질문이면 필요한 전문 agent tool을 모두 호출하세요.
- 같은 질문을 여러 전문 agent에 중복 위임하지 마세요.
- 전문 agent 선택이 애매하면 가장 직접적인 하나만 호출하세요.
- 전문 agent tool 결과에 없는 부동산 사실, 가격, 법령 내용을 추측하지 마세요.
- 지원 범위 밖 질문이면 tool을 호출하지 않아도 됩니다.

전문 agent 선택 기준:
- lookup_agent: 단지 위치, 주소, 실거래 내역, 최고가 같은 단순 조회
- recommendation_agent: 지역, 가격, 역세권, 신축, 세대수 조건 기반 아파트 추천
- comparison_agent: 둘 이상의 아파트 가격, 평형, 연식, 교통, 교육 비교
- price_trend_agent: 시세 추이, 가격 변화율, 가격 순위 분석
- legal_contract_agent: 부동산 계약, 매매, 전세, 임대차, 법령 근거 질문
""".strip()


ToolBuilder = Callable[[Session], Any]


@dataclass(frozen=True)
class SpecialistAgentSpec:
  name: str
  description: str
  tool_builders: tuple[ToolBuilder, ...]
  system_prompt: str


@dataclass(frozen=True)
class SpecialistAgentResult:
  agent: str
  result: dict[str, Any]

  @property
  def success(self) -> bool:
    return self.result.get("success") is True

  def to_dict(self) -> dict[str, Any]:
    return {
      "agent": self.agent,
      "success": self.success,
      "result": self.result,
    }


SPECIALIST_AGENT_SPECS = [
  SpecialistAgentSpec(
    name="lookup_agent",
    description="단지 위치, 주소, 실거래 내역, 최고가 같은 단순 조회 담당",
    tool_builders=(build_simple_lookup_tool,),
    system_prompt=f"{CHATBOT_AGENT_SYSTEM_PROMPT}\n\n당신은 단순 조회 전문 Agent입니다. 단지 위치, 주소, 실거래 내역, 최고가 질문만 simple_lookup tool로 처리하세요.",
  ),
  SpecialistAgentSpec(
    name="recommendation_agent",
    description="지역, 가격, 역세권, 신축, 세대수 조건 기반 아파트 추천 담당",
    tool_builders=(build_recommendation_tool,),
    system_prompt=f"{CHATBOT_AGENT_SYSTEM_PROMPT}\n\n당신은 아파트 추천 전문 Agent입니다. 조건 기반 추천 질문만 recommend_apartments tool로 처리하세요.",
  ),
  SpecialistAgentSpec(
    name="comparison_agent",
    description="둘 이상의 아파트 가격, 평형, 연식, 교통, 교육 비교 담당",
    tool_builders=(build_comparison_tool,),
    system_prompt=f"{CHATBOT_AGENT_SYSTEM_PROMPT}\n\n당신은 아파트 비교 전문 Agent입니다. 둘 이상의 단지 비교 질문만 compare_apartments tool로 처리하세요.",
  ),
  SpecialistAgentSpec(
    name="price_trend_agent",
    description="시세 추이, 가격 변화율, 가격 순위 분석 담당",
    tool_builders=(build_price_trend_tool,),
    system_prompt=f"{CHATBOT_AGENT_SYSTEM_PROMPT}\n\n당신은 시세 추이 전문 Agent입니다. 가격 추이, 변동률, 순위 질문만 analyze_price_trend tool로 처리하세요.",
  ),
  SpecialistAgentSpec(
    name="legal_contract_agent",
    description="부동산 계약, 매매, 전세, 임대차, 법령 근거 질문 담당",
    tool_builders=(build_legal_contract_tool,),
    system_prompt=f"{CHATBOT_AGENT_SYSTEM_PROMPT}\n\n당신은 부동산 계약 법령 전문 Agent입니다. 계약/법령 근거 질문만 search_legal_contract tool로 처리하세요.",
  ),
]


class SpecialistChatbotAgent:
  def __init__(self, session: Session, spec: SpecialistAgentSpec, model: str | None = None):
    self.name = spec.name
    self.spec = spec
    self.agent = create_agent(
      model=model or os.getenv("OPENAI_CHAT_MODEL", DEFAULT_AGENT_MODEL),
      tools=[builder(session) for builder in spec.tool_builders],
      system_prompt=spec.system_prompt,
    )

  async def run(self, question: str) -> dict[str, Any]:
    result = await self.agent.ainvoke({
      "messages": [{"role": "user", "content": question}],
    })
    return extract_agent_result(result)

  def as_tool(self) -> StructuredTool:
    async def run_specialist(query: str) -> dict[str, Any]:
      """Run a specialist agent for the provided user query."""
      return SpecialistAgentResult(
        agent=self.name,
        result=await self.run(query),
      ).to_dict()

    return StructuredTool.from_function(
      coroutine=run_specialist,
      name=self.name,
      description=self.spec.description,
    )


class ChatbotSupervisor:
  def __init__(self, session: Session, model: str | None = None):
    self.specialists = [
      SpecialistChatbotAgent(session, spec, model=model)
      for spec in SPECIALIST_AGENT_SPECS
    ]
    self.supervisor = create_agent(
      model=model or os.getenv("OPENAI_CHAT_MODEL", DEFAULT_AGENT_MODEL),
      tools=[specialist.as_tool() for specialist in self.specialists],
      system_prompt=SUPERVISOR_AGENT_SYSTEM_PROMPT,
    )

  async def run(self, question: str) -> dict[str, Any]:
    result = await self.supervisor.ainvoke({
      "messages": [{"role": "user", "content": question}],
    })
    return extract_supervisor_result(result)


ChatbotAgent = ChatbotSupervisor


def extract_supervisor_result(result: dict[str, Any]) -> dict[str, Any]:
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

  specialist_results = []
  for tool_result in tool_results:
    agent_name = tool_result.get("agent")
    specialist_result = tool_result.get("result")
    if not isinstance(agent_name, str) or not isinstance(specialist_result, dict):
      return tool_result_parse_failed_result()
    specialist_results.append(SpecialistAgentResult(
      agent=agent_name,
      result=specialist_result,
    ))

  if len(specialist_results) == 1:
    return specialist_results[0].result
  return aggregate_specialist_results(specialist_results)


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


def aggregate_specialist_results(specialist_results: list[SpecialistAgentResult]) -> dict[str, Any]:
  total = len(specialist_results)
  succeeded = sum(1 for item in specialist_results if item.success)
  failed = total - succeeded
  results = [item.to_dict() for item in specialist_results]

  if succeeded == total:
    return {
      "success": True,
      "status": "success",
      "message": "여러 전문 에이전트 결과를 처리했습니다.",
      "results": results,
      "executionSummary": execution_summary(total, succeeded, failed),
    }
  if succeeded > 0:
    return {
      "success": True,
      "status": "partial_success",
      "message": "일부 전문 에이전트 결과만 처리했습니다.",
      "results": results,
      "executionSummary": execution_summary(total, succeeded, failed),
    }
  return {
    "success": False,
    "status": "failed",
    "reason": "all_specialist_agents_failed",
    "message": "전문 에이전트 결과를 처리하지 못했습니다.",
    "results": results,
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
