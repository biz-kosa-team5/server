from fastapi.testclient import TestClient

from app.chatbot.service.splitter import split_question
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
from app.main import app


client = TestClient(app)


def test_chatbot_splitter_separates_multi_intent_questions():
  assert split_question("30억 이하 아파트 추천하고 매매 계약 법률 알려줘") == [
    "30억 이하 아파트",
    "매매 계약 법률 알려줘",
  ]


def test_recommendation_extractor_builds_filter_slots():
  slots = extract_recommendation_slots("서초역 근처 30억 이하 신축 아파트 추천해줘")

  assert slots["station_name"] == "서초역"
  assert slots["max_price"] == 300000
  assert slots["is_new_build"] is True
  assert slots["min_built_year"] == 2020
  assert slots["radius_m"] == 800
  assert slots["sort_by"] == "distance_asc"


def test_recommendation_extractor_keeps_district_and_price_words_distinct():
  cheap_slots = extract_recommendation_slots("서초구 20억 이하 저렴한 아파트 4곳 추천해줘")
  expensive_slots = extract_recommendation_slots("청담역 주변 비싼 아파트 3개 추천해줘")

  assert cheap_slots["district"] == "서초구"
  assert cheap_slots["limit"] == 4
  assert cheap_slots["sort_by"] == "price_asc"
  assert "school_type" not in cheap_slots
  assert expensive_slots["station_name"] == "청담역"
  assert expensive_slots["sort_by"] == "price_desc"


def test_comparison_extractor_builds_subject_and_metric_slots():
  slots = extract_compare_slots("래미안대치팰리스랑 잠실엘스 가격 비교해줘")

  assert slots["apartment_names"] == ["래미안대치팰리스", "잠실엘스"]
  assert slots["metrics"] == ["latest_price", "pyeong", "price_per_pyeong"]


def test_comparison_extractor_cleans_metric_words_from_names():
  assert extract_compare_slots("반포자이랑 래미안퍼스티지 초등학교 접근성 비교해줘")["apartment_names"] == [
    "반포자이",
    "래미안퍼스티지",
  ]
  assert extract_compare_slots("아크로리버파크랑 래미안원펜타스 가격이랑 평당가 비교해줘")["apartment_names"] == [
    "아크로리버파크",
    "래미안원펜타스",
  ]
  assert extract_compare_slots("도곡렉슬이랑 대치현대 어디가 더 대단지야 비교해줘")["apartment_names"] == [
    "도곡렉슬",
    "대치현대",
  ]


def test_chatbot_query_returns_no_matching_tool_response(monkeypatch):
  class FakeChatbotAgent:
    def __init__(self, _):
      pass

    async def run(self, __):
      return {
        "success": False,
        "reason": "no_matching_tool",
        "message": "현재 챗봇은 부동산 단지 조회, 아파트 추천, 단지 비교, 시세 추이, 계약 관련 법령 질문을 처리할 수 있습니다.",
      }

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotAgent", FakeChatbotAgent)

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "잠실엘스 어디 있어?"},
  )

  assert response.status_code == 200
  payload = response.json()
  assert payload["success"] is False
  assert payload["fragments"][0]["status"] == "not_handled"
  assert "intent" not in payload["fragments"][0]
  assert payload["result"]["reason"] == "no_matching_tool"


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
