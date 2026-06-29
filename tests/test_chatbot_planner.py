from app.chatbot.service.planner import build_execution_plan


def handlers(plan):
  return [step.handler for step in plan.steps]


def test_planner_routes_clear_recommendation_to_single_feature():
  plan = build_execution_plan("송파구 30억 이하 아파트 추천해줘")

  assert plan.plan_type == "single_feature"
  assert handlers(plan) == ["recommendation"]


def test_planner_routes_candidate_comparison_as_dependent_multi_feature():
  plan = build_execution_plan("강남구 아파트 추천하고 후보 비교도 해줘")

  assert plan.plan_type == "dependent_multi_feature"
  assert handlers(plan) == ["recommendation", "comparison"]
  assert plan.steps[1].depends_on == "recommendation_agent"


def test_planner_routes_nearby_station_apartment_comparison_as_dependent_multi_feature():
  plan = build_execution_plan("잠실역이랑 가까운 아파트들을 비교해줘")

  assert plan.plan_type == "dependent_multi_feature"
  assert plan.reason == "nearby_candidates_feed_comparison"
  assert handlers(plan) == ["recommendation", "comparison"]
  assert plan.steps[1].depends_on == "recommendation_agent"


def test_planner_routes_plain_complex_price_as_ambiguous_multi_feature():
  plan = build_execution_plan("잠실엘스 시세 알려줘")

  assert plan.plan_type == "ambiguous_multi_feature"
  assert handlers(plan) == ["simple_lookup", "price_trend"]
  assert plan.steps[0].slot_overrides["target_name"] == "잠실엘스"
  assert plan.steps[1].slot_overrides == {
    "analysis_type": "timeseries",
    "target_type": "complex",
    "target_name": "잠실엘스",
    "period": "1y",
  }


def test_planner_routes_recommendation_and_legal_as_independent_multi_feature():
  plan = build_execution_plan("강남구 아파트 추천하고 매매 계약 법령도 알려줘")

  assert plan.plan_type == "independent_multi_feature"
  assert handlers(plan) == ["recommendation", "legal_contract"]


def test_planner_excludes_lookup_only_and_trend_only_from_ambiguous_price():
  lookup_plan = build_execution_plan("잠실엘스 최근 실거래가 알려줘")
  trend_plan = build_execution_plan("잠실엘스 시세 추이 알려줘")

  assert lookup_plan.plan_type == "single_feature"
  assert handlers(lookup_plan) == ["simple_lookup"]
  assert trend_plan.plan_type == "single_feature"
  assert handlers(trend_plan) == ["price_trend"]


def test_planner_routes_same_tool_multi_region_target_directly():
  plan = build_execution_plan("강남구 시세추이랑 송파구 시세추이 알려줘")

  assert plan.plan_type == "same_tool_multi_feature"
  assert handlers(plan) == ["price_trend", "price_trend"]
  assert [step.slot_overrides["target_name"] for step in plan.steps] == ["강남구", "송파구"]


def test_planner_routes_same_tool_multi_complex_target_directly():
  plan = build_execution_plan("잠실엘스랑 래미안대치팰리스 시세추이 알려줘")

  assert plan.plan_type == "same_tool_multi_feature"
  assert handlers(plan) == ["price_trend", "price_trend"]
  assert [step.slot_overrides["target_name"] for step in plan.steps] == ["잠실엘스", "래미안대치팰리스"]


def test_planner_keeps_price_comparison_as_comparison_not_same_tool_trend():
  plan = build_execution_plan("래미안대치팰리스와 잠실엘스 가격 비교해줘")

  assert plan.plan_type == "single_feature"
  assert handlers(plan) == ["comparison"]


def test_planner_routes_indirect_comparison_phrases_to_comparison():
  plan = build_execution_plan("래미안대치팰리스랑 잠실엘스 중 어디가 초등학교에 가까워?")

  assert plan.plan_type == "single_feature"
  assert handlers(plan) == ["comparison"]


def test_planner_routes_station_apartment_lookup_like_recommendation():
  plan = build_execution_plan("서초역 근처 아파트 알려줘")

  assert plan.plan_type == "single_feature"
  assert handlers(plan) == ["recommendation"]


def test_planner_keeps_ambiguous_price_multi_complex_target_for_supervisor():
  plan = build_execution_plan("잠실엘스랑 래미안대치팰리스 시세 알려줘")

  assert plan.plan_type == "supervisor_llm"
  assert plan.reason == "same_tool_multi_target"


def test_planner_keeps_recommendation_candidate_lookup_as_unsupported_dependent_chain():
  plan = build_execution_plan("강남구 아파트 추천하고 후보 실거래도 알려줘")

  assert plan.plan_type == "supervisor_llm"
  assert plan.reason == "unsupported_dependent_chain"


def test_planner_builds_supported_unsupported_multi_feature_plan():
  plan = build_execution_plan("잠실엘스 위치랑 오늘 날씨 알려줘")

  assert plan.plan_type == "supported_unsupported_multi_feature"
  assert [(step.handler, step.query) for step in plan.steps] == [
    ("simple_lookup", "잠실엘스 위치 알려줘"),
    ("no_matching_tool", "오늘 날씨 알려줘"),
  ]


def test_planner_routes_pure_unsupported_question_to_no_matching_tool():
  plan = build_execution_plan("오늘 날씨 알려줘")

  assert plan.plan_type == "unsupported_feature"
  assert [(step.agent, step.handler, step.query) for step in plan.steps] == [
    ("unsupported_agent", "no_matching_tool", "오늘 날씨 알려줘"),
  ]


def test_planner_does_not_force_ranking_price_trend_to_timeseries():
  plan = build_execution_plan("최근 1년 강남구에서 많이 오른 아파트 TOP 5 알려줘")

  assert plan.plan_type == "single_feature"
  assert handlers(plan) == ["price_trend"]
  assert plan.steps[0].slot_overrides == {
    "target_type": "region",
    "target_name": "강남구",
  }


def test_planner_cleans_lookup_period_words_from_target_name():
  plan = build_execution_plan("래미안대치팰리스 최근 1년 거래 내역 보여줘")

  assert plan.plan_type == "single_feature"
  assert handlers(plan) == ["simple_lookup"]
  assert plan.steps[0].slot_overrides["target_name"] == "래미안대치팰리스"


def test_planner_extracts_lookup_target_after_leading_query_phrase():
  plan = build_execution_plan("최근 실거래가 래미안대치팰리스 알려줘")

  assert plan.plan_type == "single_feature"
  assert handlers(plan) == ["simple_lookup"]
  assert plan.steps[0].slot_overrides["target_name"] == "래미안대치팰리스"


def test_planner_routes_legal_questions_with_plain_legal_terms():
  plan = build_execution_plan("소유권 이전등기는 어떤 법과 관련 있어?")

  assert plan.plan_type == "single_feature"
  assert handlers(plan) == ["legal_contract"]


def test_planner_routes_family_money_question_to_legal_contract():
  plan = build_execution_plan("부모님이 돈을 보태주면 문제가 있어?")

  assert plan.plan_type == "single_feature"
  assert handlers(plan) == ["legal_contract"]


def test_planner_keeps_new_record_question_out_of_legal_contract():
  plan = build_execution_plan("신고가 TOP 5 알려줘")

  assert plan.plan_type == "unsupported_feature"
  assert handlers(plan) == ["no_matching_tool"]


def test_planner_routes_region_price_record_to_lookup_not_recommendation():
  plan = build_execution_plan("서초구에서 가장 비싼 아파트 보여줘")

  assert plan.plan_type == "single_feature"
  assert handlers(plan) == ["simple_lookup"]
  assert plan.steps[0].slot_overrides == {
    "target_name": "서초구",
    "query_type": "region_price_ranking",
    "price_order": "highest",
  }


def test_planner_builds_sub_queries_for_independent_comparison_and_legal():
  plan = build_execution_plan("래미안대치팰리스랑 잠실엘스 비교하고 계약 시 주의할 법도 알려줘")

  assert plan.plan_type == "independent_multi_feature"
  assert [(step.handler, step.query) for step in plan.steps] == [
    ("comparison", "래미안대치팰리스랑 잠실엘스 비교해줘"),
    ("legal_contract", "계약 시 주의할 법도 알려줘"),
  ]


def test_planner_keeps_recommendation_lookup_without_fake_region_trade_target():
  plan = build_execution_plan("강남구 아파트 추천하고 실거래도 알려줘")

  assert plan.plan_type == "independent_multi_feature"
  assert [(step.handler, step.query, step.slot_overrides) for step in plan.steps] == [
    ("recommendation", "강남구 아파트 추천해줘", {}),
    ("simple_lookup", "실거래도 알려줘", {"query_type": "trade_history"}),
  ]


def test_planner_keeps_unsupported_dependent_chain_for_supervisor():
  plan = build_execution_plan("송파구 30억 이하 추천하고 추천 후보들 가격 흐름도 알려줘")

  assert plan.plan_type == "supervisor_llm"
  assert plan.reason == "unsupported_dependent_chain"
