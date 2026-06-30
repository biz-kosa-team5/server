import json

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def parse_sse_events(text: str) -> list[dict[str, object]]:
  events = []
  for frame in text.strip().split("\n\n"):
    if not frame.strip():
      continue
    event_type = None
    data_lines = []
    for line in frame.splitlines():
      if line.startswith("event:"):
        event_type = line.removeprefix("event:").strip()
      elif line.startswith("data:"):
        data_lines.append(line.removeprefix("data:").strip())
    events.append({
      "event": event_type,
      "data": json.loads("\n".join(data_lines)),
    })
  return events


def install_successful_stream_mocks(monkeypatch, answer: str = "잠실엘스는 송파구 잠실동에 있는 단지입니다."):
  class FakeChatbotSupervisor:
    def __init__(self, _session, model=None):
      self.model = model

    async def run(self, _question):
      return {
        "success": True,
        "handler": "simple_lookup",
        "query_type": "location",
        "criteria": {
          "target_name": "잠실엘스",
        },
        "data": [
          {
            "complex_id": 1002,
            "complex_name": "잠실엘스",
            "address": "서울특별시 송파구 잠실동",
            "latitude": 37.5124,
            "longitude": 127.0821,
          },
        ],
      }

  class FakeChatbotAnswerComposer:
    def __init__(self, model=None):
      self.model = model
      self.last_usage = None

    async def compose(self, _context):
      return answer

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotSupervisor", FakeChatbotSupervisor)
  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotAnswerComposer", FakeChatbotAnswerComposer)


def test_chatbot_stream_rejects_blank_question():
  response = client.post(
    "/api/v1/chatbot/query/stream",
    json={"question": "   "},
  )

  assert response.status_code == 422
  assert response.json()["detail"][0]["msg"] == "Value error, 질문을 입력해 주세요."


def test_chatbot_stream_response_contract(monkeypatch):
  install_successful_stream_mocks(monkeypatch)

  response = client.post(
    "/api/v1/chatbot/query/stream",
    json={"question": "잠실엘스 위치 알려줘"},
  )

  assert response.status_code == 200
  assert response.headers["content-type"].startswith("text/event-stream")
  assert response.headers["cache-control"] == "no-cache"
  assert response.headers["x-accel-buffering"] == "no"

  events = parse_sse_events(response.text)
  event_types = [event["event"] for event in events]
  assert event_types[:5] == ["status", "status", "status", "status", "status"]
  assert event_types[5] == "artifacts"
  assert "answer_delta" in event_types[6:-1]
  assert event_types[-1] == "final"

  status_payloads = [
    event["data"]
    for event in events
    if event["event"] == "status"
  ]
  assert status_payloads == [
    {"label": "질문 분석 중", "step": 1, "total": 5},
    {"label": "작업 분리 중", "step": 2, "total": 5},
    {"label": "작업 1/1 처리 중", "step": 3, "total": 5},
    {"label": "지도/시각 자료 준비 중", "step": 4, "total": 5},
    {"label": "답변 문장 정리 중", "step": 5, "total": 5},
  ]

  artifacts = events[5]["data"]
  assert artifacts["uiActions"][0]["id"] == "focus_map:complex:1002"
  assert artifacts["uiArtifacts"] == []
  assert artifacts["uiSummary"]["hasMapFocus"] is True


def test_chatbot_stream_final_matches_existing_response_shape(monkeypatch):
  install_successful_stream_mocks(monkeypatch)

  response = client.post(
    "/api/v1/chatbot/query/stream",
    json={"question": "잠실엘스 위치 알려줘"},
  )

  events = parse_sse_events(response.text)
  final = events[-1]["data"]
  assert final["success"] is True
  assert final["status"] == "success"
  assert final["question"] == "잠실엘스 위치 알려줘"
  assert final["fragments"][0]["status"] == "handled"
  assert final["result"]["handler"] == "simple_lookup"
  assert final["message"] == "질문을 처리했습니다."
  assert final["executionSummary"] == {
    "total": 1,
    "succeeded": 1,
    "failed": 0,
  }
  assert final["answer"] == "잠실엘스는 송파구 잠실동에 있는 단지입니다."
  assert final["uiActions"][0]["id"] == "focus_map:complex:1002"
  assert final["uiSummary"]["hasMapFocus"] is True


def test_chatbot_stream_answer_delta_hides_internal_terms_and_raw_coordinates(monkeypatch):
  install_successful_stream_mocks(
    monkeypatch,
    answer=(
      "잠실엘스 위치를 찾았습니다. "
      "handler tool execution planType "
      '{"latitude":37.5124,"longitude":127.0821}'
    ),
  )

  response = client.post(
    "/api/v1/chatbot/query/stream",
    json={"question": "잠실엘스 위치 알려줘"},
  )

  events = parse_sse_events(response.text)
  streamed_answer = "".join(
    event["data"]["text"]
    for event in events
    if event["event"] == "answer_delta"
  )
  assert streamed_answer
  for forbidden in ("handler", "tool", "execution", "planType", "37.5124", "127.0821", "{", "}"):
    assert forbidden not in streamed_answer


def test_chatbot_stream_returns_error_event_on_internal_exception(monkeypatch):
  install_successful_stream_mocks(monkeypatch)

  def fake_build_chatbot_ui_payload(_session, _response_dict):
    raise RuntimeError("boom")

  monkeypatch.setattr(
    "app.chatbot.service.chatbot_service.build_chatbot_ui_payload",
    fake_build_chatbot_ui_payload,
  )

  response = client.post(
    "/api/v1/chatbot/query/stream",
    json={"question": "잠실엘스 위치 알려줘"},
  )

  events = parse_sse_events(response.text)
  assert events[-1] == {
    "event": "error",
    "data": {"message": "AI 집찾기 응답을 불러오지 못했습니다."},
  }
