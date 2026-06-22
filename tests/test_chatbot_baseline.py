import pytest
from fastapi.testclient import TestClient

from app.chatbot.types import Intent
from app.chatbot.service.chatbot_service import handle_fragment
from app.chatbot.service.classifier import (
  EmbeddingIntentClassifier,
  IntentClassification,
  classify_intent,
)
from app.chatbot.service.splitter import split_question
from app.chatbot.features.comparison import extract_compare_slots
from app.chatbot.features.recommendation import extract_recommendation_slots
from app.main import app


client = TestClient(app)


class FakeEmbeddingClient:
  model = "fake-embedding"
  dimensions = 2

  def __init__(self, vectors: dict[str, list[float]]):
    self.vectors = vectors

  def prepare_text(self, text: str) -> str:
    return text.strip().lower()

  def embed(self, texts: list[str]) -> list[list[float]]:
    return [self.vectors[text] for text in texts]


def test_chatbot_classifier_routes_docs_intents():
  assert classify_intent("서초역 근처 30억 이하 신축 아파트 추천해줘") == Intent.RECOMMENDATION
  assert classify_intent("래미안대치팰리스랑 잠실엘스 가격 비교해줘") == Intent.COMPARISON
  assert classify_intent("잠실엘스 어디 있어?") == Intent.SIMPLE_LOOKUP
  assert classify_intent("최근 많이 오른 아파트 알려줘") == Intent.PRICE_TREND
  assert classify_intent("매매 계약 시 확인할 법률 알려줘") == Intent.LEGAL_CONTRACT
  assert classify_intent("오늘 점심 뭐 먹지?") == Intent.UNSUPPORTED


def test_chatbot_classifier_does_not_treat_connectors_as_comparison_intent():
  assert classify_intent("은마아파트 위치랑 잠실엘스 시세 알려줘") == Intent.SIMPLE_LOOKUP
  assert classify_intent("강남구와 서초구 아파트 추천해줘") == Intent.RECOMMENDATION
  assert classify_intent("법원역 근처 아파트 추천해줘") == Intent.RECOMMENDATION


def test_embedding_intent_classifier_uses_top_k_majority_vote():
  reference_sentences = {
    Intent.RECOMMENDATION: ("recommend near station", "recommend by budget"),
    Intent.COMPARISON: ("compare exact match",),
  }
  classifier = EmbeddingIntentClassifier(
    FakeEmbeddingClient({
      "recommend near station": [0.9, 0.1],
      "recommend by budget": [0.8, 0.2],
      "compare exact match": [1.0, 0.0],
      "recommend question": [1.0, 0.0],
    }),
    reference_sentences=reference_sentences,
    k=3,
    threshold=0.55,
  )

  classification = classifier.classify("recommend question")

  assert classification.intent == Intent.RECOMMENDATION
  assert classification.confidence == pytest.approx(0.9938837346736189)


def test_embedding_intent_classifier_returns_unsupported_below_threshold():
  classifier = EmbeddingIntentClassifier(
    FakeEmbeddingClient({
      "legal contract": [1.0, 0.0],
      "unrelated": [0.0, 1.0],
    }),
    reference_sentences={Intent.LEGAL_CONTRACT: ("legal contract",)},
    k=1,
    threshold=0.55,
  )

  classification = classifier.classify("unrelated")

  assert classification.intent == Intent.UNSUPPORTED
  assert classification.confidence == pytest.approx(0.0)


def test_chatbot_fragment_includes_classifier_confidence(monkeypatch):
  monkeypatch.setattr(
    "app.chatbot.service.chatbot_service.classify_intent_with_confidence",
    lambda _: IntentClassification(Intent.SIMPLE_LOOKUP, 0.77),
  )

  fragment = handle_fragment(None, 0, "잠실엘스 알려줘")

  assert fragment["intent"] == "simple_lookup"
  assert fragment["status"] == "not_implemented"
  assert fragment["confidence"] == 0.77


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
