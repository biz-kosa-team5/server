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
from .dedupe import dedupe_specialist_results, dedupe_tool_results


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
- 전문 agent와 tool의 description/인자 설명을 보고 질문 전체 의미에 가장 맞는 tool을 스스로 선택하세요.
- 특정 단어 하나만 보고 고정 라우팅하지 마세요. 예를 들어 "찾아줘"는 대상이 특정 단지면 위치/기본 조회일 수 있고, 조건이 붙은 아파트 탐색이면 추천일 수 있습니다.
- 질문 안에 서로 다른 종류의 근거가 필요해 보이면 여러 전문 agent tool 호출을 고려하세요.
- 특정 단지명과 함께 "정보", "알려줘", "요약", "개요"처럼 포괄적으로 묻는 질문은 단지 위치/기본 정보, 최근 거래, 최근 가격 흐름을 함께 보는 질문으로 해석하고 lookup_agent와 price_trend_agent 호출을 고려하세요.
- 추천과 함께 시세/가격 흐름, 실거래/위치, 후보 비교, 계약/법령 근거를 함께 묻는 경우 관련 전문 agent를 추가로 호출할 수 있습니다.
- "추천 이유"처럼 recommendation_agent 결과만으로 설명 가능한 경우에는 recommendation_agent 하나로 충분합니다.
- 하나의 전문 agent로 충분하면 하나만 호출하세요.
- 서로 다른 관측이 필요하면 여러 specialist agent를 호출할 수 있습니다.
- 같은 의미의 동일 agent/tool 중복 호출은 금지합니다.
- 같은 tool이라도 대상이나 조건이 다르면 각각 호출할 수 있습니다.
- 전문 agent 선택이 애매하고 서로 다른 관측이 명확하지 않으면 가장 직접적인 하나만 호출하세요.
- 전문 agent tool 결과에 없는 부동산 사실, 가격, 법령 내용을 추측하지 마세요.
- 지원 범위 밖 질문이면 tool을 호출하지 않아도 됩니다.

전문 agent 선택 기준:
- lookup_agent: 단지 위치, 주소, 실거래 내역, 최고가 같은 단순 조회
- recommendation_agent: 지역, 가격, 역세권, 학교/학군/초중고, 신축, 세대수 조건 기반 아파트 추천
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
  depends_on: str | None = None
  trace: dict[str, Any] | None = None

  @property
  def success(self) -> bool:
    return self.result.get("success") is True

  def to_dict(self, *, include_trace: bool = False) -> dict[str, Any]:
    value = {
      "agent": self.agent,
      "success": self.success,
      "result": self.result,
    }
    if self.depends_on:
      value["dependsOn"] = self.depends_on
    if include_trace and self.trace:
      value["trace"] = self.trace
    return value


def specialist_system_prompt(role: str, responsibility: str, tool_name: str) -> str:
  return (
    f"{CHATBOT_AGENT_SYSTEM_PROMPT}\n\n"
    f"당신은 {role} 전문 Agent입니다. "
    f"{responsibility} 질문만 {tool_name} tool로 처리하세요. "
    "질문이 짧거나 붙여 쓰였거나 오타가 있어도 원문 전체 의미를 보고 가능한 tool 인자를 직접 채우세요. "
    "단지명은 사용자가 쓴 문자열을 후보로 넘기고, 실제 존재 여부 판단은 tool 결과에 맡기세요."
  )


SPECIALIST_AGENT_SPECS = [
  SpecialistAgentSpec(
    name="lookup_agent",
    description=(
      "특정 단지 찾기/위치/주소, 단지 실거래 내역, 동/구 최신 실거래, 최고가 조회 담당, "
      "이 agent의 query에는 사용자의 원문 질문을 그대로 넣어야 함"
      "질문을 요약하거나 재작성하지 말고, 기간(예: 지난 1년/최근 6개월), 면적(예: 84㎡/30평), "
      "정렬 조건(예: 최고가/최저가/최근순), 개수 조건(예: 3건/5개만)을 절대 제거하지 말 것"
    ),
    tool_builders=(build_simple_lookup_tool,),
    system_prompt=specialist_system_prompt(
      "단순 조회",
      "단지 위치, 주소, 실거래 내역, 최고가",
      "simple_lookup",
    ),
  ),
  SpecialistAgentSpec(
    name="recommendation_agent",
    description="지역, 가격, 역세권, 학교/학군/초중고, 생활편의, 신축, 세대수 조건 기반 아파트 탐색/추천 담당",
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
    description=(
      "시세 추이, 가격 변화율, 가격 순위 분석 담당, "
      "이 agent의 query에는 사용자의 원문 질문을 그대로 넣어야 함. "
      "질문을 요약하거나 재작성하지 말고, 기간(예: 2024년/최근 1년), 면적(예: 84㎡/30평), "
      "정렬 조건(예: 상승률/하락률/순위), 개수 조건(예: 3개만/TOP 5)을 절대 제거하지 말 것"
    ),
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
    self.model = model or os.getenv("OPENAI_CHAT_MODEL", DEFAULT_AGENT_MODEL)
    self.agent = create_agent(
      model=self.model,
      tools=[builder(session) for builder in spec.tool_builders],
      system_prompt=spec.system_prompt,
    )

  async def run(self, question: str) -> dict[str, Any]:
    result, _trace = await self.run_with_trace(question)
    return result

  async def run_with_trace(self, question: str) -> tuple[dict[str, Any], dict[str, Any]]:
    result = await self.agent.ainvoke({
      "messages": [{"role": "user", "content": question}],
    })
    return extract_agent_result(result), agent_execution_trace(result, model=self.model)

  def as_tool(self) -> StructuredTool:
    async def run_specialist(query: str) -> dict[str, Any]:
      """Run a specialist agent for the provided user query."""
      if hasattr(self, "agent"):
        result, trace = await self.run_with_trace(query)
      else:
        result = await self.run(query)
        trace = {}
      return SpecialistAgentResult(
        agent=self.name,
        result=result,
        trace=trace,
      ).to_dict(include_trace=True)

    return StructuredTool.from_function(
      coroutine=run_specialist,
      name=self.name,
      description=self.spec.description,
    )


class ChatbotSupervisor:
  def __init__(self, session: Session, model: str | None = None):
    self.model = model or os.getenv("OPENAI_CHAT_MODEL", DEFAULT_AGENT_MODEL)
    self.specialists = [
      SpecialistChatbotAgent(session, spec, model=self.model)
      for spec in SPECIALIST_AGENT_SPECS
    ]
    self.supervisor = create_agent(
      model=self.model,
      tools=[specialist.as_tool() for specialist in self.specialists],
      system_prompt=SUPERVISOR_AGENT_SYSTEM_PROMPT,
    )

  async def run(self, question: str) -> dict[str, Any]:
    result, _execution = await self.run_with_trace(question)
    return result

  async def run_with_trace(self, question: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    result = await self.supervisor.ainvoke({
      "messages": [{"role": "user", "content": build_supervisor_user_content(question)}],
    })
    return extract_supervisor_result_with_trace(result)


ChatbotAgent = ChatbotSupervisor


def build_supervisor_user_content(question: str) -> str:
  return question


def extract_supervisor_result(result: dict[str, Any]) -> dict[str, Any]:
  supervisor_result, _execution = extract_supervisor_result_with_trace(result)
  return supervisor_result


def extract_supervisor_result_with_trace(result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
  tool_messages = [
    message
    for message in result.get("messages", [])
    if getattr(message, "type", None) == "tool"
  ]
  tool_results = parse_tool_messages(tool_messages)
  supervisor_usage = collect_usage_metadata(result)

  if not tool_messages:
    execution = {"path": "supervisor_no_tool"}
    if supervisor_usage:
      execution["usage"] = supervisor_usage
      execution["supervisorUsage"] = supervisor_usage
    return no_matching_tool_result(), execution

  specialist_results = []
  for tool_result in tool_results:
    specialist_results.append(specialist_result_from_tool_result(tool_result))
  specialist_results, deduplicated_count = dedupe_specialist_results(specialist_results)
  specialist_traces = [
    item.trace
    for item in specialist_results
    if item.trace
  ]
  total_usage = merge_token_usage(
    supervisor_usage,
    *[
      trace.get("usage")
      for trace in specialist_traces
      if isinstance(trace, dict)
    ],
  )

  if len(specialist_results) == 1:
    specialist_result = specialist_results[0]
    execution = {
      "path": "specialist_tool",
      "selectedAgent": specialist_result.agent,
    }
    if deduplicated_count:
      execution["deduplicatedCount"] = deduplicated_count
    enrich_usage_trace(
      execution,
      total_usage=total_usage,
      supervisor_usage=supervisor_usage,
      specialist_traces=specialist_traces,
    )
    return (
      specialist_result.result,
      execution,
    )
  execution = {
    "path": "supervisor_aggregate",
    "selectedAgents": [item.agent for item in specialist_results],
  }
  if deduplicated_count:
    execution["deduplicatedCount"] = deduplicated_count
  enrich_usage_trace(
    execution,
    total_usage=total_usage,
    supervisor_usage=supervisor_usage,
    specialist_traces=specialist_traces,
  )
  return (
    aggregate_specialist_results(specialist_results),
    execution,
  )


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
  trace = tool_result.get("trace")
  if isinstance(agent_name, str) and isinstance(specialist_result, dict):
    return SpecialistAgentResult(
      agent=agent_name,
      result=specialist_result,
      trace=trace if isinstance(trace, dict) else None,
    )
  return SpecialistAgentResult(
    agent=agent_name if isinstance(agent_name, str) else "unknown_agent",
    result=tool_result_parse_failed_result(),
    trace=trace if isinstance(trace, dict) else None,
  )


def aggregate_tool_results(tool_messages: list[Any], tool_results: list[dict[str, Any]]) -> dict[str, Any]:
  tool_results, _deduplicated_count = dedupe_tool_results(tool_results)
  if len(tool_results) == 1:
    return tool_results[0]

  total = len(tool_results)
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
  specialist_results, _deduplicated_count = dedupe_specialist_results(specialist_results)
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


def agent_execution_trace(result: dict[str, Any], *, model: str) -> dict[str, Any]:
  trace: dict[str, Any] = {"model": model}
  usage = collect_usage_metadata(result)
  if usage:
    trace["usage"] = usage
  tool_names = collect_tool_names(result)
  if tool_names:
    trace["toolCalls"] = tool_names
  return trace


def collect_tool_names(result: dict[str, Any]) -> list[str]:
  messages = result.get("messages", [])
  names: list[str] = []
  if not isinstance(messages, list):
    return names
  for message in messages:
    if get_message_value(message, "type") != "tool":
      continue
    name = get_message_value(message, "name")
    if isinstance(name, str) and name and name not in names:
      names.append(name)
  return names


def collect_usage_metadata(result: dict[str, Any]) -> dict[str, int] | None:
  messages = result.get("messages", [])
  if not isinstance(messages, list):
    return None
  usages = []
  for message in messages:
    usage = usage_from_message(message)
    if usage:
      usages.append(usage)
  return merge_token_usage(*usages)


def usage_from_message(message: Any) -> dict[str, int] | None:
  usage = get_message_value(message, "usage_metadata")
  normalized = normalize_token_usage(usage)
  if normalized:
    return normalized

  response_metadata = get_message_value(message, "response_metadata")
  if isinstance(response_metadata, dict):
    for key in ("token_usage", "usage", "usage_metadata"):
      normalized = normalize_token_usage(response_metadata.get(key))
      if normalized:
        return normalized
  return None


def normalize_token_usage(value: Any) -> dict[str, int] | None:
  if not isinstance(value, dict):
    return None
  input_tokens = int_or_zero(
    value.get("input_tokens")
    or value.get("prompt_tokens")
  )
  output_tokens = int_or_zero(
    value.get("output_tokens")
    or value.get("completion_tokens")
  )
  total_tokens = int_or_zero(value.get("total_tokens"))
  if total_tokens == 0:
    total_tokens = input_tokens + output_tokens

  cached_tokens = 0
  input_details = value.get("input_token_details")
  if isinstance(input_details, dict):
    cached_tokens = int_or_zero(
      input_details.get("cache_read")
      or input_details.get("cached_tokens")
    )
  prompt_details = value.get("prompt_tokens_details")
  if isinstance(prompt_details, dict):
    cached_tokens = max(
      cached_tokens,
      int_or_zero(
        prompt_details.get("cached_tokens")
        or prompt_details.get("cache_read")
      ),
    )

  if input_tokens == 0 and output_tokens == 0 and total_tokens == 0:
    return None
  return {
    "input_tokens": input_tokens,
    "output_tokens": output_tokens,
    "cached_tokens": cached_tokens,
    "total_tokens": total_tokens,
  }


def merge_token_usage(*usages: dict[str, Any] | None) -> dict[str, int] | None:
  total = {
    "input_tokens": 0,
    "output_tokens": 0,
    "cached_tokens": 0,
    "total_tokens": 0,
  }
  found = False
  for usage in usages:
    normalized = normalize_token_usage(usage)
    if not normalized:
      continue
    found = True
    for key in total:
      total[key] += normalized.get(key, 0)
  return total if found else None


def enrich_usage_trace(
  execution: dict[str, Any],
  *,
  total_usage: dict[str, int] | None,
  supervisor_usage: dict[str, int] | None,
  specialist_traces: list[dict[str, Any]],
) -> None:
  if total_usage:
    execution["usage"] = total_usage
  if supervisor_usage:
    execution["supervisorUsage"] = supervisor_usage
  if specialist_traces:
    execution["specialistTraces"] = specialist_traces


def get_message_value(value: Any, key: str) -> Any:
  if isinstance(value, dict):
    return value.get(key)
  return getattr(value, key, None)


def int_or_zero(value: Any) -> int:
  try:
    return int(value)
  except (TypeError, ValueError):
    return 0


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
