from app.chatbot.features.comparison import extract_compare_slots
from app.chatbot.features.recommendation import extract_recommendation_slots
from app.chatbot.service.tools import (
  build_comparison_tool,
  build_legal_contract_tool,
  build_price_trend_tool,
  build_recommendation_tool,
  build_simple_lookup_tool,
)
from app.database import SessionLocal, ensure_initialized


def test_recommendation_extractor_builds_filter_slots():
  slots = extract_recommendation_slots("서초역 근처 30억 이하 신축 아파트 추천해줘")

  assert slots["station_name"] == "서초역"
  assert slots["max_price"] == 300000
  assert slots["is_new_build"] is True
  assert slots["min_built_year"] == 2020
  assert slots["radius_m"] == 800
  assert slots["sort_by"] == "distance_asc"


def test_recommendation_extractor_does_not_treat_connector_go_as_high_school():
  slots = extract_recommendation_slots("강남구에 있는 아파트 3개를 추천해주고 그 이유를 알려줘")

  assert slots == {
    "district": "강남구",
    "limit": 3,
  }


def test_recommendation_extractor_keeps_school_shorthand_when_tokenized():
  slots = extract_recommendation_slots("초/중/고 가까운 강남구 아파트 3개 추천해줘")

  assert slots["school_types"] == ["초등학교", "중학교", "고등학교"]
  assert slots["radius_m"] == 800
  assert slots["limit"] == 3


def test_comparison_extractor_builds_subject_and_metric_slots():
  slots = extract_compare_slots("래미안대치팰리스랑 잠실엘스 가격 비교해줘")

  assert slots["apartment_names"] == ["래미안대치팰리스", "잠실엘스"]
  assert slots["metrics"] == ["latest_price", "pyeong", "price_per_pyeong"]


def test_simple_lookup_tool_calls_existing_service():
  ensure_initialized()
  with SessionLocal() as session:
    result = build_simple_lookup_tool(session).invoke({"query": "잠실엘스 어디 있어?"})

  assert result["handler"] == "simple_lookup"
  assert result["success"] is True
  assert result["query_type"] == "location"


def test_simple_lookup_tool_overrides_extracted_slots():
  ensure_initialized()
  with SessionLocal() as session:
    result = build_simple_lookup_tool(session).invoke({
      "query": "잠실 엘스 시세 알려줘",
      "query_type": "location",
      "complex_name": "잠실엘스",
    })

  assert result["handler"] == "simple_lookup"
  assert result["success"] is True
  assert result["query_type"] == "location"
  assert result["criteria"]["complex_name"] == "잠실엘스"


def test_feature_tools_are_langchain_tools():
  ensure_initialized()
  with SessionLocal() as session:
    tools = [
      build_simple_lookup_tool(session),
      build_recommendation_tool(session),
      build_comparison_tool(session),
      build_price_trend_tool(session),
      build_legal_contract_tool(session),
    ]

  assert [tool.name for tool in tools] == [
    "simple_lookup",
    "recommend_apartments",
    "compare_apartments",
    "analyze_price_trend",
    "search_legal_contract",
  ]
  assert all(tool.description for tool in tools)
