from fastapi.testclient import TestClient

from app.chatbot.service.splitter import split_question
from app.chatbot.service.agent import SUPPORTED_QUESTION_EXAMPLES, extract_agent_result
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


class FakeAgentMessage:
  def __init__(self, message_type, content):
    self.type = message_type
    self.content = content


def test_chatbot_splitter_separates_explicit_connectors():
  assert split_question("잠실엘스 위치 알려줘 그리고 매매 계약 법률 알려줘") == [
    "잠실엘스 위치 알려줘",
    "매매 계약 법률 알려줘",
  ]


def test_chatbot_splitter_keeps_intent_verbs_inside_fragment():
  assert split_question("30억 이하 아파트 추천하고 매매 계약 법률 알려줘") == [
    "30억 이하 아파트 추천하고 매매 계약 법률 알려줘",
  ]


def test_recommendation_extractor_builds_filter_slots():
  slots = extract_recommendation_slots("서초역 근처 30억 이하 신축 아파트 추천해줘")

  assert slots["station_name"] == "서초역"
  assert slots["max_price"] == 300000
  assert slots["is_new_build"] is True
  assert slots["min_built_year"] == 2020
  assert slots["radius_m"] == 800
  assert slots["sort_by"] == "distance_asc"


def test_comparison_extractor_builds_subject_and_metric_slots():
  slots = extract_compare_slots("래미안대치팰리스랑 잠실엘스 가격 비교해줘")

  assert slots["apartment_names"] == ["래미안대치팰리스", "잠실엘스"]
  assert slots["metrics"] == ["latest_price", "pyeong", "price_per_pyeong"]


def test_chatbot_query_returns_no_matching_tool_response(monkeypatch):
  class FakeChatbotAgent:
    def __init__(self, _):
      pass

    async def run(self, __):
      return {
        "success": False,
        "reason": "no_matching_tool",
        "message": "지원 가능한 질문은 단지 조회, 아파트 추천, 단지 비교, 시세 추이, 계약 법령 질문입니다.",
        "suggestedQuestions": SUPPORTED_QUESTION_EXAMPLES,
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
  assert payload["result"]["suggestedQuestions"] == SUPPORTED_QUESTION_EXAMPLES


def test_extract_agent_result_returns_no_matching_tool_without_tool_messages():
  result = extract_agent_result({"messages": []})

  assert result["success"] is False
  assert result["reason"] == "no_matching_tool"
  assert result["suggestedQuestions"] == SUPPORTED_QUESTION_EXAMPLES


def test_extract_agent_result_returns_parse_failure_for_unparseable_tool_message():
  result = extract_agent_result({
    "messages": [FakeAgentMessage("tool", "not json")],
  })

  assert result == {
    "success": False,
    "reason": "tool_result_parse_failed",
    "message": "조회 결과를 해석하지 못했습니다. 잠시 후 다시 시도해 주세요.",
  }


def test_extract_agent_result_parses_tool_message_json():
  result = extract_agent_result({
    "messages": [FakeAgentMessage("tool", '{"success": true, "handler": "simple_lookup"}')],
  })

  assert result == {
    "success": True,
    "handler": "simple_lookup",
  }


def test_chatbot_query_rejects_blank_question():
  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "   "},
  )

  assert response.status_code == 422
  assert response.json()["detail"][0]["msg"] == "Value error, 질문을 입력해 주세요."


def test_chatbot_query_trims_question_before_service(monkeypatch):
  captured = {}

  async def fake_handle_chatbot_query(_session, payload):
    captured["payload"] = payload
    return {
      "success": False,
      "question": payload["question"],
      "fragments": [],
      "result": {
        "success": False,
        "reason": "no_matching_tool",
      },
      "message": "처리할 수 있는 질문이 없습니다.",
    }

  monkeypatch.setattr(
    "app.chatbot.controller.chatbot_controller.handle_chatbot_query",
    fake_handle_chatbot_query,
  )

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "  잠실엘스 어디 있어?  "},
  )

  assert response.status_code == 200
  assert captured["payload"]["question"] == "잠실엘스 어디 있어?"
  assert response.json()["question"] == "잠실엘스 어디 있어?"


def test_chatbot_query_returns_initialization_failure_reason(monkeypatch):
  class FakeChatbotAgent:
    def __init__(self, _):
      raise RuntimeError("boom")

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotAgent", FakeChatbotAgent)

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "잠실엘스 어디 있어?"},
  )

  assert response.status_code == 200
  payload = response.json()
  assert payload["success"] is False
  assert payload["fragments"][0]["status"] == "not_handled"
  assert payload["result"]["reason"] == "agent_initialization_failed"
  assert payload["result"]["message"] == "챗봇 실행 준비 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."


def test_chatbot_query_returns_execution_failure_reason(monkeypatch):
  class FakeChatbotAgent:
    def __init__(self, _):
      pass

    async def run(self, __):
      raise RuntimeError("boom")

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotAgent", FakeChatbotAgent)

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "잠실엘스 어디 있어?"},
  )

  assert response.status_code == 200
  payload = response.json()
  assert payload["success"] is False
  assert payload["fragments"][0]["status"] == "not_handled"
  assert payload["result"]["reason"] == "agent_execution_failed"
  assert payload["result"]["message"] == "질문 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."


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
