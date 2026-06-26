from fastapi.testclient import TestClient
import pytest

from app.chatbot.service.answer import ChatbotAnswerContext
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

  assert context.to_dict() == response


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
    json={"question": "잠실엘스 어디 있어?"},
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


def test_chatbot_query_uses_supervisor_for_single_domain_question(monkeypatch):
  calls = []

  class FakeChatbotSupervisor:
    def __init__(self, _):
      pass

    async def run(self, question):
      calls.append(question)
      return {
        "success": True,
        "handler": "simple_lookup",
      }

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotSupervisor", FakeChatbotSupervisor)

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "잠실엘스 위치 알려줘"},
  )

  assert response.status_code == 200
  assert calls == ["잠실엘스 위치 알려줘"]
  assert response.json()["answer"] == "질문을 처리했습니다."
  assert response.json()["result"] == {
    "success": True,
    "handler": "simple_lookup",
  }


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

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotSupervisor", FakeChatbotSupervisor)

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
  assert payload["result"] == [
    {
      "success": True,
      "handler": "simple_lookup",
    },
    {
      "success": False,
      "reason": "no_matching_tool",
    },
  ]
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


def test_chatbot_query_returns_initialization_failure_reason(monkeypatch):
  class FakeChatbotSupervisor:
    def __init__(self, _):
      raise RuntimeError("boom")

  monkeypatch.setattr("app.chatbot.service.chatbot_service.ChatbotSupervisor", FakeChatbotSupervisor)

  response = client.post(
    "/api/v1/chatbot/query",
    json={"question": "잠실엘스 어디 있어?"},
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
    json={"question": "잠실엘스 어디 있어?"},
  )

  assert response.status_code == 200
  payload = response.json()
  assert payload["success"] is False
  assert payload["answer"] == "처리할 수 있는 질문이 없습니다."
  assert payload["fragments"][0]["status"] == "not_handled"
  assert payload["result"]["reason"] == "agent_execution_failed"
  assert payload["result"]["message"] == "질문 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
