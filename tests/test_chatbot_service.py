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


def test_chatbot_query_uses_supervisor_for_single_lookup_question(monkeypatch):
  calls = []
  supervisor_calls = []

  class FakeChatbotSupervisor:
    def __init__(self, _):
      pass

    async def run(self, question):
      supervisor_calls.append(question)
      return {
        "success": True,
        "handler": "simple_lookup",
        "query_type": "location",
        "criteria": {
          "target_name": "잠실엘스",
        },
      }

  def fake_run_simple_lookup(_session, slots, text):
    calls.append((slots, text))
    raise AssertionError("direct fallback should not run when supervisor selects a tool")

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotSupervisor", FakeChatbotSupervisor)
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_simple_lookup", fake_run_simple_lookup)

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "잠실엘스 위치 알려줘"},
  )

  assert response.status_code == 200
  assert calls == []
  assert supervisor_calls == ["잠실엘스 위치 알려줘"]
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
    "path": "specialist_tool",
    "planType": "single_feature",
    "selectedAgent": "lookup_agent",
    "handler": "simple_lookup",
  }


def test_chatbot_query_resolves_contextual_question_before_execution(monkeypatch):
  supervisor_calls = []

  class FakeChatbotSupervisor:
    def __init__(self, _):
      pass

    async def run(self, question):
      supervisor_calls.append(question)
      return {
        "success": True,
        "handler": "price_trend",
        "observation_type": "timeseries",
        "criteria": {
          "target_type": "complex",
          "target_name": "래미안대치팰리스",
        },
        "row_count": 0,
        "rows": [],
      }

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotSupervisor", FakeChatbotSupervisor)

  response = client.post(
    "/api/v1/chatbot/query",
    json={
      "question": "두 번째 거 최근 1년 흐름도 알려줘",
      "conversationContext": {
        "version": "v1",
        "items": [
          {
            "index": 1,
            "kind": "complex",
            "complexId": 3810,
            "complexName": "풍림아이원2차202동",
          },
          {
            "index": 2,
            "kind": "complex",
            "complexId": 1001,
            "complexName": "래미안대치팰리스",
          },
        ],
      },
    },
  )

  assert response.status_code == 200
  payload = response.json()
  assert supervisor_calls == ["래미안대치팰리스 최근 1년 흐름도 알려줘"]
  assert payload["question"] == "두 번째 거 최근 1년 흐름도 알려줘"
  assert payload["resolvedQuestion"] == "래미안대치팰리스 최근 1년 흐름도 알려줘"
  assert payload["conversationResolution"]["source"] == "ordinal_item"


def test_chatbot_query_adds_ui_payload_before_composing_answer(monkeypatch):
  captured_context = {}

  class CapturingAnswerComposer:
    async def compose(self, context):
      captured_context["context"] = context
      return "잠실엘스 위치를 지도에 표시했습니다."

  class FakeChatbotSupervisor:
    def __init__(self, _):
      pass

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
            "latitude": 37.5124,
            "longitude": 127.0821,
          }
        ],
      }

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotAnswerComposer", CapturingAnswerComposer)
  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotSupervisor", FakeChatbotSupervisor)

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


def test_chatbot_query_initializes_supervisor_for_lookup(monkeypatch):
  class FakeChatbotSupervisor:
    def __init__(self, _):
      pass

    async def run(self, _question):
      return {
        "success": True,
        "handler": "simple_lookup",
        "query_type": "location",
        "criteria": {
          "target_name": "잠실엘스",
        },
        "message": "단지 위치를 조회했습니다.",
      }

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotSupervisor", FakeChatbotSupervisor)

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "잠실엘스 위치 알려줘"},
  )

  assert response.status_code == 200
  assert response.json()["success"] is True
  assert response.json()["fragments"][0]["execution"]["path"] == "specialist_tool"


def test_chatbot_query_uses_direct_lookup_when_supervisor_initialization_fails(monkeypatch):
  class FakeChatbotSupervisor:
    def __init__(self, _):
      raise RuntimeError("boom")

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
  assert response.json()["fragments"][0]["execution"]["fallbackFrom"] == "supervisor"
  assert response.json()["fragments"][0]["execution"]["fallbackReason"] == "supervisor_initialization_failed"


def test_chatbot_query_uses_direct_fallback_when_supervisor_selects_no_tool(monkeypatch):
  supervisor_calls = []

  class FakeChatbotSupervisor:
    def __init__(self, _):
      pass

    async def run(self, question):
      supervisor_calls.append(question)
      return {
        "success": False,
        "reason": "no_matching_tool",
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
  assert supervisor_calls == ["송파구 30억 이하 아파트 추천해줘"]
  assert payload["result"]["handler"] == "recommendation"
  assert payload["fragments"][0]["execution"] == {
    "path": "direct_feature",
    "planType": "single_feature",
    "selectedAgent": "recommendation_agent",
    "handler": "recommendation",
    "fallbackFrom": "supervisor",
    "fallbackReason": "supervisor_no_tool",
  }


def test_chatbot_query_uses_direct_fallback_when_supervisor_misses_multi_handler(monkeypatch):
  class FakeChatbotSupervisor:
    def __init__(self, _):
      pass

    async def run_with_trace(self, _question):
      return (
        {
          "success": True,
          "status": "partial_success",
          "results": [
            {
              "agent": "recommendation_agent",
              "success": True,
              "result": {
                "success": True,
                "handler": "recommendation",
                "results": [{"complexName": "잠실엘스"}],
              },
            },
            {
              "agent": "comparison_agent",
              "success": False,
              "result": {
                "success": False,
                "reason": "no_matching_tool",
              },
            },
          ],
        },
        {
          "path": "supervisor_aggregate",
          "selectedAgents": ["recommendation_agent", "comparison_agent"],
        },
      )

  def fake_run_recommendation(_session, slots, text):
    return {
      "success": True,
      "handler": "recommendation",
      "criteria": slots,
      "question": text,
      "results": [
        {"complexName": "잠실엘스"},
        {"complexName": "래미안대치팰리스"},
      ],
    }

  def fake_run_comparison(_session, slots, _text):
    return {
      "success": True,
      "handler": "comparison",
      "criteria": {"apartment_names": slots["apartment_names"]},
      "results": [
        {"name": name}
        for name in slots["apartment_names"]
      ],
    }

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotSupervisor", FakeChatbotSupervisor)
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_recommendation", fake_run_recommendation)
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_comparison", fake_run_comparison)

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "강남구 아파트 추천하고 후보 비교도 해줘"},
  )

  assert response.status_code == 200
  payload = response.json()
  execution = payload["fragments"][0]["execution"]
  assert execution["path"] == "direct_dependent_features"
  assert execution["fallbackFrom"] == "supervisor"
  assert execution["fallbackReason"] == "supervisor_missing_required_handlers"
  assert execution["handlerCalls"] == ["recommendation", "comparison"]
  assert payload["result"]["results"][1]["dependsOn"] == "recommendation_agent"
  assert payload["result"]["results"][1]["result"]["handler"] == "comparison"


def test_chatbot_query_uses_direct_fallback_when_supervisor_misses_ambiguous_price_trend(monkeypatch):
  class FakeChatbotSupervisor:
    def __init__(self, _):
      pass

    async def run(self, _question):
      return {
        "success": True,
        "handler": "simple_lookup",
        "query_type": "trade_history",
        "criteria": {
          "target_name": "잠실엘스",
        },
      }

  def fake_run_simple_lookup(_session, slots, text):
    return {
      "success": True,
      "handler": "simple_lookup",
      "query_type": slots["query_type"],
      "criteria": {"target_name": slots["target_name"]},
      "question": text,
      "data": [],
    }

  def fake_run_price_trend(_session, slots):
    return {
      "success": True,
      "handler": "price_trend",
      "criteria": slots,
      "rows": [],
      "row_count": 0,
    }

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotSupervisor", FakeChatbotSupervisor)
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_simple_lookup", fake_run_simple_lookup)
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_price_trend", fake_run_price_trend)

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "잠실엘스 시세 알려줘"},
  )

  assert response.status_code == 200
  payload = response.json()
  execution = payload["fragments"][0]["execution"]
  assert execution["path"] == "direct_ambiguous_features"
  assert execution["fallbackFrom"] == "supervisor"
  assert execution["fallbackReason"] == "supervisor_missing_required_handlers"
  assert execution["handlerCalls"] == ["simple_lookup", "price_trend"]


def test_chatbot_query_expands_generic_complex_profile_when_supervisor_only_returns_location(monkeypatch):
  class FakeChatbotSupervisor:
    def __init__(self, _):
      pass

    async def run(self, _question):
      return {
        "success": True,
        "handler": "simple_lookup",
        "query_type": "location",
        "criteria": {
          "target_name": "은마",
        },
        "data": [
          {
            "complex_name": "은마",
            "address": "대치동 316",
            "latitude": 37.49,
            "longitude": 127.06,
          },
        ],
      }

  def fake_run_simple_lookup(_session, slots, text):
    return {
      "success": True,
      "handler": "simple_lookup",
      "query_type": slots["query_type"],
      "criteria": {"target_name": slots["target_name"]},
      "question": text,
      "data": [],
    }

  def fake_run_price_trend(_session, slots):
    return {
      "success": True,
      "handler": "price_trend",
      "criteria": slots,
      "rows": [],
      "row_count": 0,
    }

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotSupervisor", FakeChatbotSupervisor)
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_simple_lookup", fake_run_simple_lookup)
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_price_trend", fake_run_price_trend)

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "은마 아파트 정보를 줘봐"},
  )

  assert response.status_code == 200
  payload = response.json()
  execution = payload["fragments"][0]["execution"]
  assert execution["path"] == "direct_ambiguous_features"
  assert execution["planType"] == "ambiguous_multi_feature"
  assert execution["fallbackFrom"] == "supervisor"
  assert execution["fallbackReason"] == "supervisor_missing_required_handlers"
  assert execution["handlerCalls"] == ["simple_lookup", "simple_lookup", "price_trend"]
  assert [
    wrapper["result"]["query_type"]
    for wrapper in payload["result"]["results"]
    if wrapper["result"]["handler"] == "simple_lookup"
  ] == ["location", "trade_history"]


def test_chatbot_query_does_not_use_direct_fallback_when_selected_tool_fails(monkeypatch):
  class FakeChatbotSupervisor:
    def __init__(self, _):
      pass

    async def run(self, _question):
      return {
        "success": False,
        "handler": "simple_lookup",
        "reason": "target_not_found",
        "message": "조건에 맞는 단지를 찾지 못했습니다.",
      }

  def fake_run_simple_lookup(_session, _slots, _text):
    raise AssertionError("direct fallback should only run when supervisor cannot select a tool")

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotSupervisor", FakeChatbotSupervisor)
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_simple_lookup", fake_run_simple_lookup)

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "없는단지 위치 알려줘"},
  )

  assert response.status_code == 200
  payload = response.json()
  assert payload["success"] is False
  assert payload["result"]["reason"] == "target_not_found"
  assert payload["fragments"][0]["execution"] == {
    "path": "specialist_tool",
    "planType": "single_feature",
    "selectedAgent": "lookup_agent",
    "handler": "simple_lookup",
  }


def test_chatbot_query_does_not_use_direct_fallback_when_selected_tool_returns_no_match(monkeypatch):
  class FakeChatbotSupervisor:
    def __init__(self, _):
      pass

    async def run_with_trace(self, _question):
      return (
        {
          "success": False,
          "reason": "no_matching_tool",
          "message": "선택된 전문 agent가 처리할 수 없습니다.",
        },
        {
          "path": "specialist_tool",
          "selectedAgent": "lookup_agent",
        },
      )

  def fake_run_simple_lookup(_session, _slots, _text):
    raise AssertionError("direct fallback should not run after a selected specialist tool returns no match")

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotSupervisor", FakeChatbotSupervisor)
  monkeypatch.setattr("app.chatbot.service.orchestrator.run_simple_lookup", fake_run_simple_lookup)

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "없는단지 위치 알려줘"},
  )

  assert response.status_code == 200
  payload = response.json()
  assert payload["success"] is False
  assert payload["result"]["reason"] == "no_matching_tool"
  assert payload["fragments"][0]["execution"] == {
    "path": "specialist_tool",
    "planType": "single_feature",
    "selectedAgent": "lookup_agent",
  }


def test_chatbot_query_composes_answer_from_tool_json_without_llm(monkeypatch):
  monkeypatch.delenv("OPENAI_API_KEY", raising=False)
  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotAnswerComposer", ChatbotAnswerComposer)

  class FakeChatbotSupervisor:
    def __init__(self, _):
      pass

    async def run(self, _question):
      return {
        "success": False,
        "reason": "no_matching_tool",
      }

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
  assert payload["fragments"][0]["execution"]["fallbackFrom"] == "supervisor"
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
