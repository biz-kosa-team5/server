from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


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
      "status": "failed",
      "question": payload["question"],
      "fragments": [],
      "result": {
        "success": False,
        "reason": "no_matching_tool",
      },
      "message": "처리할 수 있는 질문이 없습니다.",
      "executionSummary": {
        "total": 0,
        "succeeded": 0,
        "failed": 0,
      },
      "answer": "처리할 수 있는 질문이 없습니다.",
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
  assert response.json()["answer"] == "처리할 수 있는 질문이 없습니다."


def test_chatbot_query_accepts_conversation_context(monkeypatch):
  captured = {}

  async def fake_handle_chatbot_query(_session, payload):
    captured["payload"] = payload
    return {
      "success": True,
      "status": "success",
      "question": payload["question"],
      "resolvedQuestion": payload["question"],
      "conversationResolution": {"applied": False},
      "conversationMemoryPatch": None,
      "fragments": [],
      "result": {
        "success": True,
        "handler": "simple_lookup",
      },
      "message": "질문을 처리했습니다.",
      "executionSummary": {
        "total": 0,
        "succeeded": 0,
        "failed": 0,
      },
      "answer": "질문을 처리했습니다.",
    }

  monkeypatch.setattr(
    "app.chatbot.controller.chatbot_controller.handle_chatbot_query",
    fake_handle_chatbot_query,
  )

  context = {
    "version": "v1",
    "activeComplex": {
      "complexId": 1001,
      "complexName": "래미안대치팰리스",
    },
  }
  response = client.post(
    "/api/v1/chatbot/query",
    json={
      "question": "그거 최근 실거래 알려줘",
      "conversationContext": context,
    },
  )

  assert response.status_code == 200
  assert captured["payload"]["conversationContext"] == context
  assert response.json()["conversationResolution"] == {"applied": False}
