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


def test_chatbot_stream_progressively_emits_recommendation_then_comparison(monkeypatch):
  def fake_recommendation(_session, _slots, _text):
    long_note = "서초구 대형마트 접근성과 생활편의 조건에 맞는 설명 " * 10
    return {
      "handler": "recommendation",
      "success": True,
      "results": [
        {
          "complexName": "서초그랑자이",
          "address": long_note,
          "latestDealAmount": 350000,
          "unitCnt": 1446,
          "useDate": "2021-06-01",
          "infrastructure": {
            "nearestStation": {"name": "교대역", "distanceM": 520},
            "nearestEducation": {"name": "서초초등학교", "distanceM": 430},
            "nearbyLifestyle": [{"name": "대형마트A", "distanceM": 420}],
          },
        },
        {
          "complexName": "래미안서초에스티지",
          "address": long_note,
          "latestDealAmount": 320000,
          "unitCnt": 421,
          "useDate": "2016-12-01",
          "infrastructure": {
            "nearestStation": {"name": "강남역", "distanceM": 610},
            "nearestEducation": {"name": "서이초등학교", "distanceM": 500},
            "nearbyLifestyle": [{"name": "대형마트B", "distanceM": 610}],
          },
        },
        {
          "complexName": "반포자이",
          "address": long_note,
          "latestDealAmount": 410000,
          "unitCnt": 3410,
          "useDate": "2009-03-01",
          "infrastructure": {
            "nearestStation": {"name": "고속터미널역", "distanceM": 700},
            "nearestEducation": {"name": "원촌초등학교", "distanceM": 650},
            "nearbyLifestyle": [{"name": "대형마트C", "distanceM": 730}],
          },
        },
      ],
    }

  def fake_comparison(_session, slots, _text):
    return {
      "handler": "comparison",
      "success": True,
      "criteria": {"apartment_names": slots["apartment_names"]},
      "results": [
        {
          "complexName": "서초그랑자이",
          "latestDealAmount": 350000,
          "pyeong": 34,
          "pricePerPyeong": 10294,
          "unitCnt": 1446,
          "builtYear": 2021,
          "nearbyLifestyle": [{"name": "대형마트A", "distanceM": 420}],
        },
        {
          "complexName": "래미안서초에스티지",
          "latestDealAmount": 320000,
          "pyeong": 34,
          "pricePerPyeong": 9411,
          "unitCnt": 421,
          "builtYear": 2016,
          "nearbyLifestyle": [{"name": "대형마트B", "distanceM": 610}],
        },
        {
          "complexName": "반포자이",
          "latestDealAmount": 410000,
          "pyeong": 34,
          "pricePerPyeong": 12058,
          "unitCnt": 3410,
          "builtYear": 2009,
          "nearbyLifestyle": [{"name": "대형마트C", "distanceM": 730}],
        },
      ],
    }

  monkeypatch.setattr("app.chatbot.service.orchestrator.run_recommendation", fake_recommendation)
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_comparison", fake_comparison)

  response = client.post(
    "/api/v1/chatbot/query/stream",
    json={"question": "근처에 대형마트가 있는 서초구 아파트를 추천해주라 3개 정도 그리고 그 3개를 비교까지 해주면 좋겠어"},
  )

  events = parse_sse_events(response.text)
  status_labels = [
    event["data"]["label"]
    for event in events
    if event["event"] == "status"
  ]
  assert status_labels == [
    "질문 의도 파악 중",
    "처리 순서 정하는 중",
    "추천 후보 찾는 중",
    "추천 후보 비교 중",
    "최종 답변 정리 중",
    "지도/시각 자료 준비 중",
  ]

  event_types = [event["event"] for event in events]
  first_answer_index = event_types.index("answer_delta")
  artifacts_index = event_types.index("artifacts")
  assert first_answer_index < artifacts_index
  streamed_answer = "".join(
    event["data"]["text"]
    for event in events
    if event["event"] == "answer_delta"
  )
  assert streamed_answer.index("먼저 조건에 맞는 추천 후보") < streamed_answer.index("이어서 위 추천 후보")
  assert streamed_answer.index("이어서 위 추천 후보") < streamed_answer.index("종합하면")
  assert len(streamed_answer) > 1000

  final = events[-1]["data"]
  assert final["answer"] == streamed_answer
  assert final["result"]["results"][1]["result"]["criteria"]["apartment_names"] == [
    "서초그랑자이",
    "래미안서초에스티지",
    "반포자이",
  ]
  for forbidden in ("전문 에이전트", "handler", "tool", "execution", "planType", "raw JSON", "latitude", "longitude", "좌표"):
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
