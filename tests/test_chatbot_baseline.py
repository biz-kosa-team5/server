from fastapi.testclient import TestClient

from app.chatbot.dto import Intent
from app.chatbot.service.classifier import classify_intent
from app.comparison.extractor import extract_compare_slots
from app.main import app
from app.recommendation.extractor import extract_recommendation_slots


client = TestClient(app)


def test_chatbot_classifier_routes_docs_intents():
  assert classify_intent("서초역 근처 30억 이하 신축 아파트 추천해줘") == Intent.RECOMMENDATION
  assert classify_intent("래미안대치팰리스랑 잠실엘스 가격 비교해줘") == Intent.COMPARISON
  assert classify_intent("잠실엘스 어디 있어?") == Intent.SIMPLE_LOOKUP
  assert classify_intent("최근 많이 오른 아파트 알려줘") == Intent.PRICE_TREND
  assert classify_intent("매매 계약 시 확인할 법률 알려줘") == Intent.LEGAL_CONTRACT
  assert classify_intent("오늘 점심 뭐 먹지?") == Intent.UNSUPPORTED


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


def test_chatbot_query_runs_recommendation_handler():
  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "송파구 40억 이하 아파트 추천해줘"},
  )

  assert response.status_code == 200
  payload = response.json()
  assert payload["success"] is True
  assert payload["fragments"][0]["intent"] == "recommendation"
  assert payload["fragments"][0]["status"] == "handled"
  assert payload["result"]["handler"] == "recommendation"
  assert [item["complexName"] for item in payload["result"]["results"]] == ["잠실엘스"]


def test_chatbot_query_runs_comparison_handler():
  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "래미안대치팰리스랑 잠실엘스 가격 비교해줘"},
  )

  assert response.status_code == 200
  payload = response.json()
  assert payload["success"] is True
  assert payload["fragments"][0]["intent"] == "comparison"
  assert payload["fragments"][0]["status"] == "handled"
  assert payload["result"]["handler"] == "comparison"
  assert [item["complexName"] for item in payload["result"]["results"]] == ["래미안대치팰리스", "잠실엘스"]


def test_chatbot_query_returns_not_implemented_for_future_handlers():
  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "잠실엘스 어디 있어?"},
  )

  assert response.status_code == 200
  payload = response.json()
  assert payload["success"] is False
  assert payload["fragments"][0]["intent"] == "simple_lookup"
  assert payload["fragments"][0]["status"] == "not_implemented"
  assert payload["result"]["reason"] == "not_implemented"


def test_chatbot_query_returns_unsupported_for_unrelated_questions():
  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "오늘 점심 뭐 먹지?"},
  )

  assert response.status_code == 200
  payload = response.json()
  assert payload["success"] is False
  assert payload["fragments"][0]["intent"] == "unsupported"
  assert payload["fragments"][0]["status"] == "unsupported"
  assert payload["result"]["reason"] == "unsupported_intent"
