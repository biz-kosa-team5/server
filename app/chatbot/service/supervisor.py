from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass
import json
import logging
import os
import re
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
- 질문 안에 서로 다른 종류의 근거가 필요해 보이면 여러 전문 agent tool 호출을 고려하세요.
- 추천과 함께 시세/가격 흐름, 실거래/위치, 후보 비교, 계약/법령 근거를 함께 묻는 경우 관련 전문 agent를 추가로 호출할 수 있습니다.
- "추천 이유"처럼 recommendation_agent 결과만으로 설명 가능한 경우에는 recommendation_agent 하나로 충분합니다.
- 하나의 전문 agent로 충분하면 하나만 호출하세요.
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
class SupervisorRoutingRule:
  agent: str
  signals: tuple[str, ...]
  reason: str


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


SUPERVISOR_ROUTING_RULES = (
  SupervisorRoutingRule(
    agent="recommendation_agent",
    signals=("추천", "권해", "골라", "조건에 맞는", "아파트 3개"),
    reason="지역, 가격, 역세권, 신축, 세대수 조건에 맞는 후보 추천",
  ),
  SupervisorRoutingRule(
    agent="lookup_agent",
    signals=("위치", "주소", "어디", "실거래", "최근 거래", "최고가"),
    reason="단지 위치, 주소, 실거래, 최고가 같은 단순 조회",
  ),
  SupervisorRoutingRule(
    agent="comparison_agent",
    signals=("비교", "차이", "vs", "둘 중", "어디가 더"),
    reason="둘 이상의 단지 비교",
  ),
  SupervisorRoutingRule(
    agent="price_trend_agent",
    signals=(
      "시세 추이",
      "가격 추이",
      "가격 흐름",
      "변화율",
      "변동률",
      "가격 순위",
      "오른",
      "내린",
    ),
    reason="시세 흐름, 가격 변화율, 순위 분석",
  ),
  SupervisorRoutingRule(
    agent="legal_contract_agent",
    signals=("계약", "법령", "법률", "임대차", "전세", "계약금", "해제", "위약금"),
    reason="부동산 계약, 매매, 전세, 임대차, 법령 근거",
  ),
)


def specialist_system_prompt(role: str, responsibility: str, tool_name: str) -> str:
  return (
    f"{CHATBOT_AGENT_SYSTEM_PROMPT}\n\n"
    f"당신은 {role} 전문 Agent입니다. "
    f"{responsibility} 질문만 {tool_name} tool로 처리하세요."
  )


SPECIALIST_AGENT_SPECS = [
  SpecialistAgentSpec(
    name="lookup_agent",
    description="단지 위치, 주소, 실거래 내역, 최고가 조회 담당",
    tool_builders=(build_simple_lookup_tool,),
    system_prompt=specialist_system_prompt(
      "단순 조회",
      "단지 위치, 주소, 실거래 내역, 최고가",
      "simple_lookup",
    ),
  ),
  SpecialistAgentSpec(
    name="recommendation_agent",
    description="지역, 가격, 역세권, 신축, 세대수 조건 기반 추천 담당",
    tool_builders=(build_recommendation_tool,),
    system_prompt=specialist_system_prompt(
      "아파트 추천",
      "조건 기반 추천",
      "recommend_apartments",
    ),
  ),
  SpecialistAgentSpec(
    name="comparison_agent",
    description="둘 이상의 아파트 가격, 평형, 연식, 교통, 교육 비교 담당",
    tool_builders=(build_comparison_tool,),
    system_prompt=specialist_system_prompt(
      "아파트 비교",
      "둘 이상의 단지 비교",
      "compare_apartments",
    ),
  ),
  SpecialistAgentSpec(
    name="price_trend_agent",
    description="시세 추이, 가격 변화율, 가격 순위 분석 담당",
    tool_builders=(build_price_trend_tool,),
    system_prompt=specialist_system_prompt(
      "시세 추이",
      "가격 추이, 변동률, 순위",
      "analyze_price_trend",
    ),
  ),
  SpecialistAgentSpec(
    name="legal_contract_agent",
    description="부동산 계약, 매매, 전세, 임대차, 법령 근거 질문 담당",
    tool_builders=(build_legal_contract_tool,),
    system_prompt=specialist_system_prompt(
      "부동산 계약 법령",
      "계약/법령 근거",
      "search_legal_contract",
    ),
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
      "messages": [{"role": "user", "content": build_supervisor_user_content(question)}],
    })
    return extract_supervisor_result(result)


ChatbotAgent = ChatbotSupervisor


def build_supervisor_user_content(question: str) -> str:
  hinted_agents = suggest_specialist_agents(question)
  if not hinted_agents:
    return question

  agent_reasons = {
    rule.agent: rule.reason
    for rule in SUPERVISOR_ROUTING_RULES
  }
  hint_lines = [
    f"- {agent}: {agent_reasons[agent]}"
    for agent in hinted_agents
  ]
  return (
    f"{question}\n\n"
    "라우팅 참고:\n"
    "질문 신호상 아래 전문 agent를 고려할 수 있습니다.\n"
    + "\n".join(hint_lines)
    + "\n이 힌트는 강제가 아니며, 실제 질문 의도에 맞는 전문 agent만 호출하세요."
  )


def suggest_specialist_agents(question: str) -> list[str]:
  normalized = normalize_question_signal_text(question)
  if not normalized:
    return []

  agents = []
  for rule in SUPERVISOR_ROUTING_RULES:
    if any(signal in normalized for signal in rule.signals):
      agents.append(rule.agent)
  return agents


def normalize_question_signal_text(question: str) -> str:
  return re.sub(r"\s+", " ", question.strip().lower())


def extract_supervisor_result(result: dict[str, Any]) -> dict[str, Any]:
  tool_messages = [
    message
    for message in result.get("messages", [])
    if getattr(message, "type", None) == "tool"
  ]
  tool_results = parse_tool_messages(tool_messages)

  if not tool_messages:
    return no_matching_tool_result()

  specialist_results = []
  for tool_result in tool_results:
    specialist_results.append(specialist_result_from_tool_result(tool_result))

  if len(specialist_results) == 1:
    return specialist_results[0].result
  return aggregate_specialist_results(specialist_results)


def extract_agent_result(result: dict[str, Any]) -> dict[str, Any]:
  tool_messages = [
    message
    for message in result.get("messages", [])
    if getattr(message, "type", None) == "tool"
  ]
  tool_results = parse_tool_messages(tool_messages)

  if not tool_messages:
    return no_matching_tool_result()
  if len(tool_messages) == 1:
    return tool_results[0]
  return aggregate_tool_results(tool_messages, tool_results)


def parse_tool_messages(tool_messages: list[Any]) -> list[dict[str, Any]]:
  return [
    parsed if parsed is not None else tool_result_parse_failed_result()
    for parsed in (
      parse_tool_message(message)
      for message in tool_messages
    )
  ]


def specialist_result_from_tool_result(tool_result: dict[str, Any]) -> SpecialistAgentResult:
  agent_name = tool_result.get("agent")
  specialist_result = tool_result.get("result")
  if isinstance(agent_name, str) and isinstance(specialist_result, dict):
    return SpecialistAgentResult(
      agent=agent_name,
      result=specialist_result,
    )
  return SpecialistAgentResult(
    agent=agent_name if isinstance(agent_name, str) else "unknown_agent",
    result=tool_result_parse_failed_result(),
  )


def aggregate_tool_results(tool_messages: list[Any], tool_results: list[dict[str, Any]]) -> dict[str, Any]:
  total = len(tool_messages)
  succeeded = sum(1 for item in tool_results if item.get("success") is True)
  failed = total - succeeded
  partial_succeeded = sum(
    1
    for item in tool_results
    if item.get("success") is True and item.get("status") == "partial_success"
  )

  if succeeded == total and partial_succeeded == 0:
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
  partial_succeeded = sum(
    1
    for item in specialist_results
    if item.success and item.result.get("status") == "partial_success"
  )
  results = [item.to_dict() for item in specialist_results]

  if succeeded == total and partial_succeeded == 0:
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
