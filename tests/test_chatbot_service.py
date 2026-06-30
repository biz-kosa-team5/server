from fastapi.testclient import TestClient
import pytest

from app.chatbot.service.answer import ChatbotAnswerComposer, ChatbotAnswerContext
from app.chatbot.service.splitter import split_question
from app.chatbot.service.chatbot_service import (
  ChatbotQueryResponse,
  ChatbotTask,
  TaskExecutionResult,
  TaskExecutionSummary,
)
from app.main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def fake_answer_composer(monkeypatch):
  class FakeChatbotAnswerComposer:
    async def compose(self, context):
      return context.message

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotAnswerComposer", FakeChatbotAnswerComposer)


def test_chatbot_splitter_separates_explicit_connectors():
  assert split_question("잠실엘스 위치 알려줘 그리고 매매 계약 법률 알려줘") == [
    "잠실엘스 위치 알려줘",
    "매매 계약 법률 알려줘",
  ]


def test_chatbot_splitter_keeps_intent_verbs_inside_fragment():
  assert split_question("30억 이하 아파트 추천하고 매매 계약 법률 알려줘") == [
    "30억 이하 아파트 추천하고 매매 계약 법률 알려줘",
  ]


def test_chatbot_task_builds_ordered_tasks_from_question():
  tasks = ChatbotTask.from_question("잠실엘스 위치 알려줘 그리고 매매 계약 법률 알려줘")

  assert tasks == [
    ChatbotTask(index=0, text="잠실엘스 위치 알려줘"),
    ChatbotTask(index=1, text="매매 계약 법률 알려줘"),
  ]


def test_task_execution_result_keeps_fragment_response_shape():
  task_result = TaskExecutionResult(
    task=ChatbotTask(index=0, text="잠실엘스 위치 알려줘"),
    result={
      "success": True,
      "handler": "simple_lookup",
    },
  )

  assert task_result.to_fragment_dict() == {
    "index": 0,
    "text": "잠실엘스 위치 알려줘",
    "status": "handled",
    "result": {
      "success": True,
      "handler": "simple_lookup",
    },
  }


def test_task_execution_summary_counts_task_results():
  summary = TaskExecutionSummary.from_task_results([
    TaskExecutionResult(
      task=ChatbotTask(index=0, text="잠실엘스 위치 알려줘"),
      result={"success": True},
    ),
    TaskExecutionResult(
      task=ChatbotTask(index=1, text="오늘 날씨 알려줘"),
      result={"success": False},
    ),
  ])

  assert summary.success is True
  assert summary.status == "partial_success"
  assert summary.message == "일부 질문만 처리했습니다."
  assert summary.to_dict() == {
    "total": 2,
    "succeeded": 1,
    "failed": 1,
  }


def test_task_execution_summary_promotes_nested_partial_success():
  summary = TaskExecutionSummary.from_task_results([
    TaskExecutionResult(
      task=ChatbotTask(index=0, text="복합 부동산 질문"),
      result={
        "success": True,
        "status": "partial_success",
        "results": [
          {"success": True, "handler": "simple_lookup"},
          {"success": False, "reason": "no_matching_tool"},
        ],
      },
    ),
  ])

  assert summary.success is True
  assert summary.status == "partial_success"
  assert summary.message == "일부 질문만 처리했습니다."
  assert summary.to_dict() == {
    "total": 1,
    "succeeded": 1,
    "failed": 0,
  }


def test_chatbot_query_response_builds_single_task_response_shape():
  response = ChatbotQueryResponse(
    question="잠실엘스 위치 알려줘",
    task_results=[
      TaskExecutionResult(
        task=ChatbotTask(index=0, text="잠실엘스 위치 알려줘"),
        result={
          "success": True,
          "handler": "simple_lookup",
        },
      ),
    ],
  ).to_response_dict()

  assert response == {
    "success": True,
    "status": "success",
    "question": "잠실엘스 위치 알려줘",
    "fragments": [
      {
        "index": 0,
        "text": "잠실엘스 위치 알려줘",
        "status": "handled",
        "result": {
          "success": True,
          "handler": "simple_lookup",
        },
      },
    ],
    "result": {
      "success": True,
      "handler": "simple_lookup",
    },
    "message": "질문을 처리했습니다.",
    "executionSummary": {
      "total": 1,
      "succeeded": 1,
      "failed": 0,
    },
  }


def test_chatbot_query_response_builds_multiple_task_response_shape():
  response = ChatbotQueryResponse(
    question="잠실엘스 위치 알려줘 그리고 오늘 날씨 알려줘",
    task_results=[
      TaskExecutionResult(
        task=ChatbotTask(index=0, text="잠실엘스 위치 알려줘"),
        result={
          "success": True,
          "handler": "simple_lookup",
        },
      ),
      TaskExecutionResult(
        task=ChatbotTask(index=1, text="오늘 날씨 알려줘"),
        result={
          "success": False,
          "reason": "no_matching_tool",
        },
      ),
    ],
  ).to_response_dict()

  assert response["success"] is True
  assert response["status"] == "partial_success"
  assert response["message"] == "일부 질문만 처리했습니다."
  assert response["result"] == [
    {
      "success": True,
      "handler": "simple_lookup",
    },
    {
      "success": False,
      "reason": "no_matching_tool",
    },
  ]
  assert response["executionSummary"] == {
    "total": 2,
    "succeeded": 1,
    "failed": 1,
  }


def test_chatbot_answer_context_keeps_existing_response_fields():
  response = {
    "success": True,
    "status": "success",
    "question": "잠실엘스 위치 알려줘",
    "fragments": [
      {
        "index": 0,
        "text": "잠실엘스 위치 알려줘",
        "status": "handled",
        "result": {
          "success": True,
          "handler": "simple_lookup",
        },
      },
    ],
    "result": {
      "success": True,
      "handler": "simple_lookup",
    },
    "message": "질문을 처리했습니다.",
    "executionSummary": {
      "total": 1,
      "succeeded": 1,
      "failed": 0,
    },
  }

  context = ChatbotAnswerContext.from_response_dict(response)

  assert context.to_dict() == {
    **response,
    "uiActions": [],
    "uiArtifacts": [],
    "uiSummary": None,
  }


def test_chatbot_query_returns_no_matching_tool_response(monkeypatch):
  class FakeChatbotSupervisor:
    def __init__(self, _):
      pass

    async def run(self, __):
      return {
        "success": False,
        "reason": "no_matching_tool",
        "message": "지원 가능한 질문은 단지 조회, 아파트 추천, 단지 비교, 시세 추이, 계약 법령 질문입니다.",
        "suggestedQuestions": [
          "잠실엘스 위치 알려줘",
          "송파구 30억 이하 아파트 추천해줘",
          "래미안대치팰리스랑 잠실엘스 가격 비교해줘",
          "최근 1년 잠실엘스 시세 추이 알려줘",
          "매매 계약금 해제 규정 알려줘",
        ],
      }

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotSupervisor", FakeChatbotSupervisor)

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "오늘 날씨 알려줘"},
  )

  assert response.status_code == 200
  payload = response.json()
  assert payload["success"] is False
  assert payload["status"] == "failed"
  assert payload["executionSummary"] == {
    "total": 1,
    "succeeded": 0,
    "failed": 1,
  }
  assert payload["answer"] == "처리할 수 있는 질문이 없습니다."
  assert payload["fragments"][0]["status"] == "not_handled"
  assert "intent" not in payload["fragments"][0]
  assert payload["result"]["reason"] == "no_matching_tool"


def test_chatbot_query_uses_direct_lookup_for_single_domain_question(monkeypatch):
  calls = []
  supervisor_calls = []

  class FakeChatbotSupervisor:
    def __init__(self, _):
      pass

    async def run(self, question):
      supervisor_calls.append(question)
      return {
        "success": False,
        "reason": "should_not_call_supervisor",
      }

  def fake_run_simple_lookup(_session, slots, text):
    calls.append((slots, text))
    return {
      "success": True,
      "handler": "simple_lookup",
      "query_type": "location",
      "criteria": {
        "target_name": slots["target_name"],
      },
    }

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotSupervisor", FakeChatbotSupervisor)
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_simple_lookup", fake_run_simple_lookup)

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "잠실엘스 위치 알려줘"},
  )

  assert response.status_code == 200
  assert calls == [({
    "original_question": "잠실엘스 위치 알려줘",
    "query_type": "location",
    "target_name": "잠실엘스",
  }, "잠실엘스 위치 알려줘")]
  assert supervisor_calls == []
  assert response.json()["answer"] == "질문을 처리했습니다."
  assert response.json()["result"] == {
    "success": True,
    "handler": "simple_lookup",
    "query_type": "location",
    "criteria": {
      "target_name": "잠실엘스",
    },
  }
  assert response.json()["fragments"][0]["execution"] == {
    "path": "direct_feature",
    "planType": "single_feature",
    "selectedAgent": "lookup_agent",
    "handler": "simple_lookup",
  }


def test_chatbot_query_adds_ui_payload_before_composing_answer(monkeypatch):
  captured_context = {}

  class CapturingAnswerComposer:
    async def compose(self, context):
      captured_context["context"] = context
      return "잠실엘스 위치를 지도에 표시했습니다."

  def fake_run_simple_lookup(_session, slots, _text):
    return {
      "success": True,
      "handler": "simple_lookup",
      "query_type": "location",
      "criteria": {
        "target_name": slots["target_name"],
      },
      "data": [
        {
          "complex_id": 1002,
          "complex_name": "잠실엘스",
          "latitude": 37.5124,
          "longitude": 127.0821,
        }
      ],
    }

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotAnswerComposer", CapturingAnswerComposer)
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_simple_lookup", fake_run_simple_lookup)

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "잠실엘스 위치 알려줘"},
  )

  assert response.status_code == 200
  payload = response.json()
  assert payload["answer"] == "잠실엘스 위치를 지도에 표시했습니다."
  assert payload["uiActions"][0]["id"] == "focus_map:complex:1002"
  assert payload["uiActions"][0]["autoRun"] is True
  assert payload["uiSummary"]["hasMapFocus"] is True
  assert captured_context["context"].uiActions[0]["id"] == "focus_map:complex:1002"


def test_chatbot_query_does_not_initialize_supervisor_for_direct_lookup(monkeypatch):
  class FakeChatbotSupervisor:
    def __init__(self, _):
      raise AssertionError("direct lookup should not initialize supervisor")

  def fake_run_simple_lookup(_session, slots, text):
    return {
      "success": True,
      "handler": "simple_lookup",
      "query_type": "location",
      "criteria": {
        "target_name": slots["target_name"],
      },
      "message": "단지 위치를 조회했습니다.",
    }

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotSupervisor", FakeChatbotSupervisor)
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_simple_lookup", fake_run_simple_lookup)

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "잠실엘스 위치 알려줘"},
  )

  assert response.status_code == 200
  assert response.json()["success"] is True
  assert response.json()["fragments"][0]["execution"]["path"] == "direct_feature"


def test_chatbot_query_marks_direct_feature_execution(monkeypatch):
  supervisor_calls = []

  class FakeChatbotSupervisor:
    def __init__(self, _):
      pass

    async def run(self, question):
      supervisor_calls.append(question)
      return {
        "success": False,
        "reason": "should_not_call_supervisor",
      }

  def fake_run_recommendation(_session, slots, text):
    return {
      "success": True,
      "handler": "recommendation",
      "criteria": slots,
      "question": text,
    }

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotSupervisor", FakeChatbotSupervisor)
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_recommendation", fake_run_recommendation)

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "송파구 30억 이하 아파트 추천해줘"},
  )

  assert response.status_code == 200
  payload = response.json()
  assert supervisor_calls == []
  assert payload["result"]["handler"] == "recommendation"
  assert payload["fragments"][0]["execution"] == {
    "path": "direct_feature",
    "planType": "single_feature",
    "selectedAgent": "recommendation_agent",
    "handler": "recommendation",
  }


def test_chatbot_query_routes_short_school_nearby_question_directly(monkeypatch):
  captured = {}

  class FakeChatbotSupervisor:
    def __init__(self, _):
      raise AssertionError("short education recommendation should not initialize supervisor")

  def fake_run_recommendation(_session, slots, text):
    captured["slots"] = slots
    captured["text"] = text
    return {
      "success": True,
      "handler": "recommendation",
      "criteria": slots,
      "results": [],
    }

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotSupervisor", FakeChatbotSupervisor)
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_recommendation", fake_run_recommendation)

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "초등학교근처"},
  )

  assert response.status_code == 200
  assert captured["text"] == "초등학교근처"
  assert captured["slots"]["school_type"] == "초등학교"
  assert captured["slots"]["sort_by"] == "school_distance_asc"
  assert response.json()["fragments"][0]["execution"]["path"] == "direct_feature"


def test_chatbot_query_composes_answer_from_tool_json_without_llm(monkeypatch):
  monkeypatch.delenv("OPENAI_API_KEY", raising=False)
  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotAnswerComposer", ChatbotAnswerComposer)

  class FakeChatbotSupervisor:
    def __init__(self, _):
      pass

    async def run(self, _question):
      raise AssertionError("direct recommendation should not call supervisor")

  def fake_run_recommendation(_session, slots, text):
    return {
      "success": True,
      "handler": "recommendation",
      "criteria": slots,
      "question": text,
      "results": [
        {
          "complexName": "잠실엘스",
          "latestDealAmountText": "28억원",
          "unitCnt": 5678,
          "useDate": "2008-09-30",
          "infrastructure": {
            "nearestStation": {
              "name": "잠실역",
              "distanceM": 420,
            },
            "nearestEducation": {
              "name": "잠일초등학교",
              "distanceM": 350,
            },
            "nearbyLifestyle": [
              {
                "name": "롯데백화점 잠실점",
                "subtype": "백화점",
                "distanceM": 760,
              },
            ],
          },
        },
      ],
      "message": "조건에 맞는 아파트를 조회했습니다.",
    }

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotSupervisor", FakeChatbotSupervisor)
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_recommendation", fake_run_recommendation)

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "송파구 30억 이하 아파트 추천해줘"},
  )

  assert response.status_code == 200
  payload = response.json()
  assert payload["answer"].startswith("조건에 맞는 추천 후보입니다.")
  assert "잠실엘스" in payload["answer"]
  assert "28억원" in payload["answer"]
  assert "잠실역" in payload["answer"]
  assert payload["fragments"][0]["execution"]["path"] == "direct_feature"
  assert nested_answer_paths(payload) == [["answer"]]


def test_chatbot_query_marks_partial_success_across_fragments(monkeypatch):
  class FakeChatbotSupervisor:
    def __init__(self, _):
      pass

    async def run(self, question):
      if "잠실엘스" in question:
        return {
          "success": True,
          "handler": "simple_lookup",
        }
      return {
        "success": False,
        "reason": "no_matching_tool",
      }

  def fake_run_simple_lookup(_session, _slots, _text):
    return {
      "success": True,
      "handler": "simple_lookup",
    }

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotSupervisor", FakeChatbotSupervisor)
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_simple_lookup", fake_run_simple_lookup)

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "잠실엘스 위치 알려줘 그리고 오늘 날씨 알려줘"},
  )

  assert response.status_code == 200
  payload = response.json()
  assert payload["success"] is True
  assert payload["status"] == "partial_success"
  assert payload["message"] == "일부 질문만 처리했습니다."
  assert payload["executionSummary"] == {
    "total": 2,
    "succeeded": 1,
    "failed": 1,
  }
  assert payload["answer"] == "일부 질문만 처리했습니다."
  assert payload["result"][0] == {
    "success": True,
    "handler": "simple_lookup",
  }
  assert payload["result"][1]["success"] is False
  assert payload["result"][1]["reason"] == "no_matching_tool"
  assert "지원 가능한 질문" in payload["result"][1]["message"]
  assert [fragment["status"] for fragment in payload["fragments"]] == [
    "handled",
    "not_handled",
  ]


def test_chatbot_query_marks_nested_partial_success(monkeypatch):
  class FakeChatbotSupervisor:
    def __init__(self, _):
      pass

    async def run(self, __):
      return {
        "success": True,
        "status": "partial_success",
        "message": "일부 전문 에이전트 결과만 처리했습니다.",
        "results": [
          {
            "success": True,
            "handler": "simple_lookup",
          },
          {
            "success": False,
            "reason": "no_matching_tool",
            "message": "지원 가능한 질문이 아닙니다.",
          },
        ],
      }

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotSupervisor", FakeChatbotSupervisor)

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "잠실엘스 위치랑 오늘 날씨 알려줘"},
  )

  assert response.status_code == 200
  payload = response.json()
  assert payload["success"] is True
  assert payload["status"] == "partial_success"
  assert payload["message"] == "일부 질문만 처리했습니다."
  assert payload["executionSummary"] == {
    "total": 1,
    "succeeded": 1,
    "failed": 0,
  }
  assert payload["answer"] == "일부 질문만 처리했습니다."
  assert payload["fragments"][0]["status"] == "handled"


def test_chatbot_query_removes_nested_answers_from_public_response(monkeypatch):
  class FakeChatbotSupervisor:
    def __init__(self, _):
      pass

    async def run(self, __):
      return {
        "success": True,
        "handler": "recommendation",
        "answer": "feature answer must not be exposed",
        "results": [
          {
            "complexName": "잠실엘스",
            "answer": "nested item answer must not be exposed",
          },
        ],
      }

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotSupervisor", FakeChatbotSupervisor)

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "부동산 정보 요약해줘"},
  )

  assert response.status_code == 200
  payload = response.json()
  assert payload["answer"] == "질문을 처리했습니다."
  assert nested_answer_paths(payload) == [["answer"]]


def test_chatbot_query_returns_initialization_failure_reason(monkeypatch):
  class FakeChatbotSupervisor:
    def __init__(self, _):
      raise RuntimeError("boom")

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotSupervisor", FakeChatbotSupervisor)

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "요즘 부동산 시장 분위기 알려줘"},
  )

  assert response.status_code == 200
  payload = response.json()
  assert payload["success"] is False
  assert payload["answer"] == "처리할 수 있는 질문이 없습니다."
  assert payload["fragments"][0]["status"] == "not_handled"
  assert payload["result"]["reason"] == "agent_initialization_failed"
  assert payload["result"]["message"] == "챗봇 실행 준비 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."


def test_chatbot_query_returns_execution_failure_reason(monkeypatch):
  class FakeChatbotSupervisor:
    def __init__(self, _):
      pass

    async def run(self, __):
      raise RuntimeError("boom")

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotSupervisor", FakeChatbotSupervisor)

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "요즘 부동산 시장 분위기 알려줘"},
  )

  assert response.status_code == 200
  payload = response.json()
  assert payload["success"] is False
  assert payload["answer"] == "처리할 수 있는 질문이 없습니다."
  assert payload["fragments"][0]["status"] == "not_handled"
  assert payload["result"]["reason"] == "agent_execution_failed"
  assert payload["result"]["message"] == "질문 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."


def nested_answer_paths(value, path=None):
  path = path or []
  paths = []
  if isinstance(value, dict):
    for key, item in value.items():
      next_path = [*path, key]
      if key == "answer":
        paths.append(next_path)
      paths.extend(nested_answer_paths(item, next_path))
  elif isinstance(value, list):
    for index, item in enumerate(value):
      paths.extend(nested_answer_paths(item, [*path, index]))
  return paths
