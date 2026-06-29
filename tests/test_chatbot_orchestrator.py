import asyncio

from app.chatbot.service.orchestrator import execute_plan
from app.chatbot.service.planner import build_execution_plan


def run_plan(question):
  return asyncio.run(execute_plan(None, question, build_execution_plan(question)))


def test_orchestrator_skips_direct_lookup_and_trend():
  lookup = asyncio.run(execute_plan(
    None,
    "잠실엘스 위치 알려줘",
    build_execution_plan("잠실엘스 위치 알려줘"),
  ))
  trend = asyncio.run(execute_plan(
    None,
    "잠실엘스 시세추이 알려줘",
    build_execution_plan("잠실엘스 시세추이 알려줘"),
  ))

  assert lookup is None
  assert trend is None


def test_orchestrator_passes_recommendation_candidates_to_comparison(monkeypatch):
  comparison_calls = []

  def fake_recommendation(_session, slots, text):
    return {
      "handler": "recommendation",
      "success": True,
      "criteria": slots,
      "results": [
        {"complexName": "잠실엘스"},
        {"complexName": "래미안대치팰리스"},
        {"complexName": "반포자이"},
      ],
      "message": "조건에 맞는 아파트를 조회했습니다.",
    }

  def fake_comparison(_session, slots, text):
    comparison_calls.append((slots, text))
    return {
      "handler": "comparison",
      "success": True,
      "criteria": {"apartment_names": slots["apartment_names"]},
      "results": [],
      "message": "아파트 비교 데이터를 조회했습니다.",
    }

  monkeypatch.setattr("app.chatbot.service.orchestrator.run_recommendation", fake_recommendation)
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_comparison", fake_comparison)

  orchestration = run_plan("강남구 아파트 추천하고 후보 비교도 해줘")

  assert comparison_calls[0][0]["apartment_names"] == ["잠실엘스", "래미안대치팰리스"]
  assert orchestration.result["status"] == "success"
  assert orchestration.execution["path"] == "direct_dependent_features"
  assert orchestration.execution["planType"] == "dependent_multi_feature"
  assert orchestration.result["results"][1]["dependsOn"] == "recommendation_agent"


def test_orchestrator_compares_three_candidates_when_requested(monkeypatch):
  comparison_calls = []

  monkeypatch.setattr("app.chatbot.service.orchestrator.run_recommendation", lambda *_: {
    "handler": "recommendation",
    "success": True,
    "results": [
      {"complexName": "잠실엘스"},
      {"complexName": "래미안대치팰리스"},
      {"complexName": "반포자이"},
    ],
  })
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_comparison", lambda _session, slots, _text: (
    comparison_calls.append(slots) or {
      "handler": "comparison",
      "success": True,
      "criteria": {"apartment_names": slots["apartment_names"]},
      "results": [],
    }
  ))

  run_plan("강남구 아파트 추천하고 후보 3개 비교도 해줘")

  assert comparison_calls[0]["apartment_names"] == ["잠실엘스", "래미안대치팰리스", "반포자이"]


def test_orchestrator_skips_comparison_when_recommendation_has_one_candidate(monkeypatch):
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_recommendation", lambda *_: {
    "handler": "recommendation",
    "success": True,
    "results": [{"complexName": "잠실엘스"}],
  })

  orchestration = run_plan("강남구 아파트 추천하고 후보 비교도 해줘")

  assert orchestration.result["status"] == "partial_success"
  comparison_wrapper = orchestration.result["results"][1]
  assert comparison_wrapper["success"] is False
  assert comparison_wrapper["dependsOn"] == "recommendation_agent"
  assert comparison_wrapper["result"]["reason"] == "insufficient_recommendation_candidates"


def test_orchestrator_skips_comparison_when_recommendation_fails(monkeypatch):
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_recommendation", lambda *_: {
    "handler": "recommendation",
    "success": False,
    "reason": "no_result",
    "message": "조건에 맞는 아파트를 찾지 못했습니다.",
  })

  orchestration = run_plan("강남구 아파트 추천하고 후보 비교도 해줘")

  assert orchestration.result["success"] is False
  assert orchestration.result["status"] == "failed"
  assert orchestration.result["results"][1]["result"]["reason"] == "dependency_failed"


def test_orchestrator_skips_lookup_and_trend_for_ambiguous_price_question(monkeypatch):
  calls = []

  def fake_lookup(_session, slots, text):
    calls.append(("lookup", slots, text))
    return {
      "handler": "simple_lookup",
      "success": True,
      "query_type": slots["query_type"],
      "criteria": {"target_name": slots["target_name"]},
      "data": [],
    }

  def fake_trend(_session, slots):
    calls.append(("trend", slots, None))
    return {
      "handler": "price_trend",
      "success": True,
      "observation_type": slots["analysis_type"],
      "criteria": slots,
      "rows": [],
      "row_count": 0,
    }

  monkeypatch.setattr("app.chatbot.service.orchestrator.run_simple_lookup", fake_lookup)
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_price_trend", fake_trend)

  orchestration = run_plan("잠실엘스 시세 알려줘")

  assert calls == []
  assert orchestration is None


def test_orchestrator_skips_price_trend_ranking_direct_execution(monkeypatch):
  calls = []

  def fake_trend(_session, slots):
    calls.append(slots)
    return {
      "handler": "price_trend",
      "success": True,
      "observation_type": slots["analysis_type"],
      "criteria": slots,
      "rows": [],
      "row_count": 0,
    }

  monkeypatch.setattr("app.chatbot.service.orchestrator.run_price_trend", fake_trend)

  orchestration = run_plan("최근 1년 강남구에서 많이 오른 아파트 TOP 5 알려줘")

  assert calls == []
  assert orchestration is None


def test_orchestrator_skips_same_tool_price_trend_multi_target(monkeypatch):
  calls = []

  def fake_trend(_session, slots):
    calls.append(slots)
    return {
      "handler": "price_trend",
      "success": True,
      "observation_type": slots["analysis_type"],
      "criteria": slots,
      "rows": [],
      "row_count": 0,
    }

  monkeypatch.setattr("app.chatbot.service.orchestrator.run_price_trend", fake_trend)

  orchestration = run_plan("강남구 시세추이랑 송파구 시세추이 알려줘")

  assert calls == []
  assert orchestration is None


def test_orchestrator_uses_sub_queries_for_independent_comparison_and_legal(monkeypatch):
  comparison_calls = []
  legal_calls = []

  def fake_comparison(_session, slots, text):
    comparison_calls.append((slots, text))
    return {
      "handler": "comparison",
      "success": True,
      "criteria": {"apartment_names": slots["apartment_names"]},
      "results": [],
    }

  def fake_legal(_session, slots, text):
    legal_calls.append((slots, text))
    return {
      "handler": "legal_contract",
      "success": True,
      "question": text,
      "sources": [],
      "message": "관련 법령 근거를 조회했습니다.",
    }

  monkeypatch.setattr("app.chatbot.service.orchestrator.run_comparison", fake_comparison)
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_legal_contract", fake_legal)

  orchestration = run_plan("래미안대치팰리스랑 잠실엘스 비교하고 계약 시 주의할 법도 알려줘")

  assert comparison_calls[0][0]["apartment_names"] == ["래미안대치팰리스", "잠실엘스"]
  assert comparison_calls[0][1] == "래미안대치팰리스랑 잠실엘스 비교해줘"
  assert legal_calls[0][1] == "계약 시 주의할 법도 알려줘"
  assert orchestration.result["status"] == "success"


def test_orchestrator_fallback_uses_step_query_for_insufficient_direct_slots(monkeypatch):
  supervisor_calls = []

  class FakeSupervisor:
    async def run(self, question):
      supervisor_calls.append(question)
      return {
        "success": False,
        "reason": "no_matching_tool",
      }

  monkeypatch.setattr("app.chatbot.service.orchestrator.run_recommendation", lambda *_: {
    "handler": "recommendation",
    "success": True,
    "results": [{"complexName": "잠실엘스"}],
  })

  orchestration = asyncio.run(execute_plan(
    None,
    "강남구 아파트 추천하고 실거래도 알려줘",
    build_execution_plan("강남구 아파트 추천하고 실거래도 알려줘"),
    supervisor=FakeSupervisor(),
  ))

  assert supervisor_calls == []
  assert orchestration is None


def test_orchestrator_skips_supported_and_unsupported_question_with_lookup(monkeypatch):
  lookup_calls = []

  def fake_lookup(_session, slots, text):
    lookup_calls.append((slots, text))
    return {
      "handler": "simple_lookup",
      "success": True,
      "query_type": "location",
      "criteria": {"target_name": slots["target_name"]},
      "data": [],
    }

  monkeypatch.setattr("app.chatbot.service.orchestrator.run_simple_lookup", fake_lookup)

  orchestration = run_plan("잠실엘스 위치랑 오늘 날씨 알려줘")

  assert lookup_calls == []
  assert orchestration is None


def test_orchestrator_directly_handles_pure_unsupported_question():
  orchestration = run_plan("오늘 날씨 알려줘")

  assert orchestration.result["success"] is False
  assert orchestration.result["reason"] == "no_matching_tool"
  assert orchestration.execution["path"] == "direct_no_matching_tool"
  assert orchestration.execution["planType"] == "unsupported_feature"
  assert orchestration.execution["handler"] == "no_matching_tool"


def test_orchestrator_marks_independent_multi_feature_partial_success(monkeypatch):
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_recommendation", lambda *_: {
    "handler": "recommendation",
    "success": True,
    "results": [{"complexName": "잠실엘스"}],
  })
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_legal_contract", lambda *_: {
    "handler": "legal_contract",
    "success": False,
    "reason": "embedding_unavailable",
    "message": "질문 임베딩을 생성할 수 없어 법령 검색을 실행하지 못했습니다.",
  })

  orchestration = run_plan("강남구 아파트 추천하고 매매 계약 법령도 알려줘")

  assert orchestration.result["success"] is True
  assert orchestration.result["status"] == "partial_success"
  assert orchestration.execution["path"] == "direct_independent_features"
  assert orchestration.execution["handlers"] == ["recommendation", "legal_contract"]
