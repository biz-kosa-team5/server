from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import re
from typing import Any

from sqlalchemy.orm import Session

from app.chatbot.features.comparison.service import run_comparison
from app.chatbot.features.comparison.slots import extract_compare_slots
from app.chatbot.features.legal_contract.service import run_legal_contract
from app.chatbot.features.legal_contract.slots import extract_legal_contract_slots
from app.chatbot.features.price_trend.service import run_price_trend
from app.chatbot.features.price_trend.slots import extract_price_trend_slots
from app.chatbot.features.recommendation.service import run_recommendation
from app.chatbot.features.recommendation.slots import extract_recommendation_slots
from app.chatbot.features.simple_lookup.service import run_simple_lookup
from app.chatbot.features.simple_lookup.slots import extract_simple_lookup_slots

from .dedupe import dedupe_specialist_results
from .planner import ExecutionPlan, FeatureStep
from .supervisor import (
  ChatbotSupervisor,
  SpecialistAgentResult,
  aggregate_specialist_results,
  agent_execution_failed_result,
  agent_initialization_failed_result,
  no_matching_tool_result,
)


SupervisorProvider = Callable[[], ChatbotSupervisor | None]


@dataclass(frozen=True)
class OrchestrationResult:
  result: dict[str, Any]
  execution: dict[str, Any]


async def execute_plan(
  session: Session,
  text: str,
  plan: ExecutionPlan,
  *,
  supervisor: ChatbotSupervisor | None = None,
  supervisor_provider: SupervisorProvider | None = None,
  supervisor_initialization_failed: bool = False,
) -> OrchestrationResult | None:
  # planner가 만든 ExecutionPlan을 실제 함수 호출로 바꾸는 실행 분기점이다.
  # planner가 "무엇을 할지" 정하면, orchestrator는 "어떻게 실행할지"를 담당한다.
  if plan.plan_type == "supervisor_llm":
    return None
  if plan.plan_type == "single_feature":
    return await execute_single_feature(session, text, plan)
  if plan.plan_type == "dependent_multi_feature":
    return execute_dependent_multi_feature(session, text, plan)
  if plan.plan_type == "ambiguous_multi_feature":
    return execute_direct_multi_feature(
      session,
      text,
      plan,
      path="direct_ambiguous_features",
    )
  if plan.plan_type == "supported_unsupported_multi_feature":
    return execute_direct_multi_feature(
      session,
      text,
      plan,
      path="direct_supported_unsupported_features",
    )
  if plan.plan_type == "unsupported_feature":
    return execute_unsupported_feature(text, plan)
  if plan.plan_type == "same_tool_multi_feature":
    return execute_direct_multi_feature(
      session,
      text,
      plan,
      path="direct_same_tool_features",
    )
  if plan.plan_type == "independent_multi_feature":
    return await execute_independent_multi_feature(
      session,
      text,
      plan,
      supervisor=supervisor,
      supervisor_provider=supervisor_provider,
      supervisor_initialization_failed=supervisor_initialization_failed,
    )
  return None


async def execute_single_feature(
  session: Session,
  text: str,
  plan: ExecutionPlan,
) -> OrchestrationResult | None:
  if len(plan.steps) != 1:
    return None

  step = plan.steps[0]
  result = run_direct_step(session, step, text)
  if result is None:
    return None

  return OrchestrationResult(
    result=result,
    execution={
      "path": "direct_feature",
      "planType": plan.plan_type,
      "selectedAgent": step.agent,
      "handler": step.handler,
    },
  )


def execute_unsupported_feature(
  text: str,
  plan: ExecutionPlan,
) -> OrchestrationResult | None:
  if len(plan.steps) != 1:
    return None

  step = plan.steps[0]
  if step.handler != "no_matching_tool":
    return None
  result = no_matching_tool_result()
  if step.query:
    result = {
      **result,
      "question": step.query,
    }

  return OrchestrationResult(
    result=result,
    execution={
      "path": "direct_no_matching_tool",
      "planType": plan.plan_type,
      "selectedAgent": step.agent,
      "handler": step.handler,
    },
  )


def execute_dependent_multi_feature(
  session: Session,
  text: str,
  plan: ExecutionPlan,
) -> OrchestrationResult:
  # 추천 결과를 먼저 만들고, 그 추천 후보 이름들을 다시 comparison 입력으로 넘기는 흐름이다.
  # 예: "잠실역 근처 아파트 추천하고 후보 비교해줘".
  recommendation_step = plan.steps[0]
  comparison_step = plan.steps[1]
  recommendation_result = run_direct_step(session, recommendation_step, text) or dependency_failed_result(
    "recommendation",
    "recommendation_not_executable",
    "추천을 실행할 수 없어 후보 비교를 진행하지 못했습니다.",
  )
  wrappers = [
    SpecialistAgentResult(
      agent=recommendation_step.agent,
      result=recommendation_result,
    )
  ]

  if recommendation_result.get("success") is not True:
    wrappers.append(SpecialistAgentResult(
      agent=comparison_step.agent,
      result=dependency_failed_result(
        "comparison",
        "dependency_failed",
        "추천 결과가 없어 후보 비교를 실행하지 못했습니다.",
      ),
      depends_on=recommendation_step.agent,
    ))
    return aggregate_orchestration_result(
      wrappers,
      plan,
      path="direct_dependent_features",
    )

  candidate_names = recommendation_candidate_names(recommendation_result)
  limit = requested_comparison_candidate_limit(text)
  candidate_names = candidate_names[:limit]
  if len(candidate_names) < 2:
    wrappers.append(SpecialistAgentResult(
      agent=comparison_step.agent,
      result=dependency_failed_result(
        "comparison",
        "insufficient_recommendation_candidates",
        "비교하려면 최소 2개 이상의 추천 후보가 필요합니다.",
      ),
      depends_on=recommendation_step.agent,
    ))
    return aggregate_orchestration_result(
      wrappers,
      plan,
      path="direct_dependent_features",
    )

  comparison_slots = extract_compare_slots(text)
  comparison_slots["apartment_names"] = candidate_names
  comparison_result = run_comparison(session, comparison_slots, text)
  wrappers.append(SpecialistAgentResult(
    agent=comparison_step.agent,
    result=comparison_result,
    depends_on=recommendation_step.agent,
  ))
  return aggregate_orchestration_result(
    wrappers,
    plan,
    path="direct_dependent_features",
  )


def execute_direct_multi_feature(
  session: Session,
  text: str,
  plan: ExecutionPlan,
  *,
  path: str,
) -> OrchestrationResult:
  wrappers = [
    SpecialistAgentResult(
      agent=step.agent,
      result=run_direct_step(session, step, text) or direct_step_not_executable_result(step),
      depends_on=step.depends_on,
    )
    for step in plan.steps
  ]
  return aggregate_orchestration_result(wrappers, plan, path=path)


async def execute_independent_multi_feature(
  session: Session,
  text: str,
  plan: ExecutionPlan,
  *,
  supervisor: ChatbotSupervisor | None,
  supervisor_provider: SupervisorProvider | None,
  supervisor_initialization_failed: bool,
) -> OrchestrationResult:
  wrappers = []
  used_supervisor_fallback = False
  for step in plan.steps:
    result = run_direct_step(session, step, text)
    if result is None:
      used_supervisor_fallback = True
      result = await run_supervisor_fallback_step(
        supervisor,
        step.query or text,
        supervisor_provider=supervisor_provider,
        supervisor_initialization_failed=supervisor_initialization_failed,
      )
    wrappers.append(SpecialistAgentResult(
      agent=step.agent,
      result=result,
      depends_on=step.depends_on,
    ))

  return aggregate_orchestration_result(
    wrappers,
    plan,
    path="hybrid_independent_features" if used_supervisor_fallback else "direct_independent_features",
  )


def run_direct_step(session: Session, step: FeatureStep, text: str) -> dict[str, Any] | None:
  query = step.query or text
  if step.handler == "no_matching_tool":
    result = no_matching_tool_result()
    if step.query:
      result = {
        **result,
        "question": step.query,
      }
    return result

  if step.handler == "recommendation":
    # 추천은 자연어를 recommendation slots로 변환한 뒤 추천 service에 넘긴다.
    slots = merge_slots(extract_recommendation_slots(query), step.slot_overrides)
    return run_recommendation(session, slots, query)

  if step.handler == "comparison":
    # 비교는 자연어에서 아파트명/비교 기준을 뽑고 comparison service에 넘긴다.
    slots = merge_slots(extract_compare_slots(query), step.slot_overrides)
    return run_comparison(session, slots, query)

  if step.handler == "simple_lookup":
    slots = merge_slots(extract_simple_lookup_slots(query), step.slot_overrides)
    if not has_required_slots(slots, ("query_type", "target_name")):
      return None
    return run_simple_lookup(session, slots, query)

  if step.handler == "price_trend":
    slots = merge_slots(extract_price_trend_slots(query), step.slot_overrides)
    if not has_required_slots(slots, ("analysis_type", "target_type", "target_name")):
      return None
    return run_price_trend(session, slots)

  if step.handler == "legal_contract":
    slots = merge_slots(extract_legal_contract_slots(query), step.slot_overrides)
    return run_legal_contract(session, slots, query)

  return None


async def run_supervisor_fallback_step(
  supervisor: ChatbotSupervisor | None,
  text: str,
  *,
  supervisor_provider: SupervisorProvider | None = None,
  supervisor_initialization_failed: bool,
) -> dict[str, Any]:
  if supervisor is None and supervisor_provider is not None:
    supervisor = supervisor_provider()
    supervisor_initialization_failed = (
      supervisor_initialization_failed
      or bool(getattr(supervisor_provider, "initialization_failed", False))
    )
  if supervisor is None:
    return (
      agent_initialization_failed_result()
      if supervisor_initialization_failed
      else agent_execution_failed_result()
    )
  try:
    return await supervisor.run(text)
  except Exception:
    return agent_execution_failed_result()


def aggregate_orchestration_result(
  wrappers: list[SpecialistAgentResult],
  plan: ExecutionPlan,
  *,
  path: str,
) -> OrchestrationResult:
  deduped, deduplicated_count = dedupe_specialist_results(wrappers)
  result = aggregate_specialist_results(deduped)
  return OrchestrationResult(
    result=result,
    execution={
      "path": path,
      "planType": plan.plan_type,
      "selectedAgents": [item.agent for item in deduped],
      "handlers": [step.handler for step in plan.steps],
      "deduplicatedCount": deduplicated_count,
    },
  )


def merge_slots(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
  slots = dict(base)
  slots.update({
    key: value
    for key, value in overrides.items()
    if value is not None
  })
  return slots


def has_required_slots(slots: dict[str, Any], keys: tuple[str, ...]) -> bool:
  return all(slots.get(key) not in (None, "", []) for key in keys)


def recommendation_candidate_names(result: dict[str, Any]) -> list[str]:
  names = []
  for item in result.get("results", []):
    if not isinstance(item, dict):
      continue
    name = item.get("complexName")
    if not isinstance(name, str) or not name.strip():
      continue
    if name not in names:
      names.append(name)
  return names


def requested_comparison_candidate_limit(text: str) -> int:
  if re.search(r"3\s*(?:개|곳|건)|세\s*(?:개|곳)", text):
    return 3
  return 2


def dependency_failed_result(handler: str, reason: str, message: str) -> dict[str, Any]:
  return {
    "handler": handler,
    "success": False,
    "reason": reason,
    "message": message,
  }


def direct_step_not_executable_result(step: FeatureStep) -> dict[str, Any]:
  return {
    "handler": step.handler,
    "success": False,
    "reason": "insufficient_slots",
    "message": "질문에서 실행에 필요한 조건을 충분히 찾지 못했습니다.",
  }
