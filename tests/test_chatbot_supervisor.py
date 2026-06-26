import asyncio

from app.chatbot.service.supervisor import (
  SUPPORTED_QUESTION_EXAMPLES,
  ChatbotAgent,
  ChatbotSupervisor,
  SpecialistChatbotAgent,
  SpecialistAgentResult,
  SPECIALIST_AGENT_SPECS,
  aggregate_specialist_results,
  extract_agent_result,
  extract_supervisor_result,
)


class FakeAgentMessage:
  def __init__(self, message_type, content):
    self.type = message_type
    self.content = content


class FakeSupervisorAgent:
  def __init__(self, result):
    self.result = result

  async def ainvoke(self, _payload):
    return self.result


def test_aggregate_specialist_results_marks_partial_success():
  result = aggregate_specialist_results([
    SpecialistAgentResult(
      agent="recommendation_agent",
      result={
        "success": True,
        "handler": "recommendation",
      },
    ),
    SpecialistAgentResult(
      agent="legal_contract_agent",
      result={
        "success": False,
        "reason": "no_matching_tool",
      },
    ),
  ])

  assert result == {
    "success": True,
    "status": "partial_success",
    "message": "일부 전문 에이전트 결과만 처리했습니다.",
    "results": [
      {
        "agent": "recommendation_agent",
        "success": True,
        "result": {
          "success": True,
          "handler": "recommendation",
        },
      },
      {
        "agent": "legal_contract_agent",
        "success": False,
        "result": {
          "success": False,
          "reason": "no_matching_tool",
        },
      },
    ],
    "executionSummary": {
      "total": 2,
      "succeeded": 1,
      "failed": 1,
    },
  }


def test_extract_supervisor_result_unwraps_single_specialist_result():
  result = extract_supervisor_result({
    "messages": [
      FakeAgentMessage(
        "tool",
        '{"agent": "recommendation_agent", "success": true, "result": {"success": true, "handler": "recommendation"}}',
      ),
    ],
  })

  assert result == {
    "success": True,
    "handler": "recommendation",
  }


def test_extract_supervisor_result_aggregates_multiple_specialist_results():
  result = extract_supervisor_result({
    "messages": [
      FakeAgentMessage(
        "tool",
        '{"agent": "recommendation_agent", "success": true, "result": {"success": true, "handler": "recommendation"}}',
      ),
      FakeAgentMessage(
        "tool",
        '{"agent": "legal_contract_agent", "success": true, "result": {"success": true, "handler": "legal_contract"}}',
      ),
    ],
  })

  assert result["success"] is True
  assert result["status"] == "success"
  assert result["executionSummary"] == {
    "total": 2,
    "succeeded": 2,
    "failed": 0,
  }
  assert [item["agent"] for item in result["results"]] == [
    "recommendation_agent",
    "legal_contract_agent",
  ]


def test_specialist_chatbot_agent_can_be_exposed_as_tool():
  specialist = SpecialistChatbotAgent.__new__(SpecialistChatbotAgent)
  specialist.name = "recommendation_agent"
  specialist.spec = SPECIALIST_AGENT_SPECS[1]

  async def fake_run(_query):
    return {
      "success": True,
      "handler": "recommendation",
    }

  specialist.run = fake_run
  tool = specialist.as_tool()

  result = asyncio.run(tool.ainvoke({"query": "송파구 30억 이하 아파트 추천해줘"}))

  assert result == {
    "agent": "recommendation_agent",
    "success": True,
    "result": {
      "success": True,
      "handler": "recommendation",
    },
  }


def test_chatbot_agent_alias_points_to_supervisor():
  assert ChatbotAgent is ChatbotSupervisor


def test_chatbot_supervisor_runs_supervisor_agent_without_langchain():
  supervisor = ChatbotSupervisor.__new__(ChatbotSupervisor)
  supervisor.supervisor = FakeSupervisorAgent({
    "messages": [
      FakeAgentMessage(
        "tool",
        '{"agent": "recommendation_agent", "success": true, "result": {"success": true, "handler": "recommendation"}}',
      ),
      FakeAgentMessage(
        "tool",
        '{"agent": "legal_contract_agent", "success": true, "result": {"success": true, "handler": "legal_contract"}}',
      ),
    ],
  })

  result = asyncio.run(supervisor.run("30억 이하 아파트 추천하고 매매 계약 법률 알려줘"))

  assert result["success"] is True
  assert result["status"] == "success"
  assert result["executionSummary"] == {
    "total": 2,
    "succeeded": 2,
    "failed": 0,
  }
  assert [item["agent"] for item in result["results"]] == [
    "recommendation_agent",
    "legal_contract_agent",
  ]


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


def test_extract_agent_result_wraps_multiple_successful_tool_results():
  result = extract_agent_result({
    "messages": [
      FakeAgentMessage("tool", '{"success": true, "handler": "simple_lookup"}'),
      FakeAgentMessage("tool", '{"success": true, "handler": "price_trend"}'),
    ],
  })

  assert result == {
    "success": True,
    "status": "success",
    "message": "여러 조회 결과를 처리했습니다.",
    "results": [
      {"success": True, "handler": "simple_lookup"},
      {"success": True, "handler": "price_trend"},
    ],
    "executionSummary": {
      "total": 2,
      "succeeded": 2,
      "failed": 0,
    },
  }


def test_extract_agent_result_marks_partial_success_for_mixed_tool_results():
  result = extract_agent_result({
    "messages": [
      FakeAgentMessage("tool", '{"success": true, "handler": "simple_lookup"}'),
      FakeAgentMessage("tool", '{"success": false, "reason": "no_result"}'),
    ],
  })

  assert result == {
    "success": True,
    "status": "partial_success",
    "message": "일부 조회 결과만 처리했습니다.",
    "results": [
      {"success": True, "handler": "simple_lookup"},
      {"success": False, "reason": "no_result"},
    ],
    "executionSummary": {
      "total": 2,
      "succeeded": 1,
      "failed": 1,
    },
  }


def test_extract_agent_result_marks_failure_when_all_tool_results_fail():
  result = extract_agent_result({
    "messages": [
      FakeAgentMessage("tool", '{"success": false, "reason": "no_result"}'),
      FakeAgentMessage("tool", '{"success": false, "reason": "invalid_request"}'),
    ],
  })

  assert result == {
    "success": False,
    "status": "failed",
    "reason": "all_tool_results_failed",
    "message": "조회 결과를 처리하지 못했습니다.",
    "results": [
      {"success": False, "reason": "no_result"},
      {"success": False, "reason": "invalid_request"},
    ],
    "executionSummary": {
      "total": 2,
      "succeeded": 0,
      "failed": 2,
    },
  }
