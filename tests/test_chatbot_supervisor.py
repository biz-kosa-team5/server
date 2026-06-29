import asyncio

from app.chatbot.service.supervisor import (
  SUPPORTED_QUESTION_EXAMPLES,
  ChatbotAgent,
  ChatbotSupervisor,
  SpecialistChatbotAgent,
  SpecialistAgentResult,
  SPECIALIST_AGENT_SPECS,
  aggregate_specialist_results,
  build_supervisor_user_content,
  extract_agent_result,
  extract_supervisor_result,
  extract_supervisor_result_with_trace,
  suggest_specialist_agents,
)


class FakeAgentMessage:
  def __init__(self, message_type, content):
    self.type = message_type
    self.content = content


class FakeSupervisorAgent:
  def __init__(self, result):
    self.result = result
    self.payloads = []

  async def ainvoke(self, payload):
    self.payloads.append(payload)
    return self.result


def test_suggest_specialist_agents_keeps_recommendation_reason_to_recommendation_agent():
  assert suggest_specialist_agents("강남구에 있는 아파트 3개를 추천해주고 그 이유를 알려줘") == [
    "recommendation_agent",
  ]


def test_suggest_specialist_agents_opens_additional_agents_for_distinct_evidence():
  assert suggest_specialist_agents("강남구 아파트 3개 추천하고 최근 시세 추이도 알려줘") == [
    "recommendation_agent",
    "price_trend_agent",
  ]
  assert suggest_specialist_agents("강남구 아파트 추천하고 실거래도 알려줘") == [
    "recommendation_agent",
    "lookup_agent",
  ]
  assert suggest_specialist_agents("강남구 아파트 추천하고 후보 비교도 해줘") == [
    "recommendation_agent",
    "comparison_agent",
  ]
  assert suggest_specialist_agents("강남구 아파트 추천하고 매매 계약 법령도 알려줘") == [
    "recommendation_agent",
    "legal_contract_agent",
  ]


def test_suggest_specialist_agents_handles_price_trend_spacing_variants():
  assert suggest_specialist_agents("잠실엘스 시세추이 알려줘") == [
    "price_trend_agent",
  ]
  assert suggest_specialist_agents("잠실엘스 시세 흐름 알려줘") == [
    "price_trend_agent",
  ]
  assert suggest_specialist_agents("잠실엘스 최근 가격 변화 알려줘") == [
    "price_trend_agent",
  ]


def test_build_supervisor_user_content_adds_non_forced_routing_hint():
  content = build_supervisor_user_content("강남구 아파트 추천하고 최근 시세 추이도 알려줘")

  assert "라우팅 참고" in content
  assert "recommendation_agent" in content
  assert "price_trend_agent" in content
  assert "강제가 아니며" in content


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


def test_aggregate_specialist_results_preserves_nested_partial_success():
  result = aggregate_specialist_results([
    SpecialistAgentResult(
      agent="recommendation_agent",
      result={
        "success": True,
        "handler": "recommendation",
      },
    ),
    SpecialistAgentResult(
      agent="lookup_agent",
      result={
        "success": True,
        "status": "partial_success",
        "message": "일부 조회 결과만 처리했습니다.",
        "results": [
          {"success": True, "handler": "simple_lookup"},
          {"success": False, "reason": "no_result"},
        ],
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
        "agent": "lookup_agent",
        "success": True,
        "result": {
          "success": True,
          "status": "partial_success",
          "message": "일부 조회 결과만 처리했습니다.",
          "results": [
            {"success": True, "handler": "simple_lookup"},
            {"success": False, "reason": "no_result"},
          ],
        },
      },
    ],
    "executionSummary": {
      "total": 2,
      "succeeded": 2,
      "failed": 0,
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


def test_extract_supervisor_result_with_trace_tracks_single_specialist_agent():
  result, execution = extract_supervisor_result_with_trace({
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
  assert execution == {
    "path": "specialist_tool",
    "selectedAgent": "recommendation_agent",
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


def test_extract_supervisor_result_marks_partial_success_for_mixed_parse_failure():
  result = extract_supervisor_result({
    "messages": [
      FakeAgentMessage(
        "tool",
        '{"agent": "recommendation_agent", "success": true, "result": {"success": true, "handler": "recommendation"}}',
      ),
      FakeAgentMessage("tool", "not json"),
    ],
  })

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
        "agent": "unknown_agent",
        "success": False,
        "result": {
          "success": False,
          "reason": "tool_result_parse_failed",
          "message": "조회 결과를 해석하지 못했습니다. 잠시 후 다시 시도해 주세요.",
        },
      },
    ],
    "executionSummary": {
      "total": 2,
      "succeeded": 1,
      "failed": 1,
    },
  }


def test_extract_supervisor_result_with_trace_tracks_aggregate_agents():
  result, execution = extract_supervisor_result_with_trace({
    "messages": [
      FakeAgentMessage(
        "tool",
        '{"agent": "recommendation_agent", "success": true, "result": {"success": true, "handler": "recommendation"}}',
      ),
      FakeAgentMessage("tool", "not json"),
    ],
  })

  assert result["status"] == "partial_success"
  assert execution == {
    "path": "supervisor_aggregate",
    "selectedAgents": [
      "recommendation_agent",
      "unknown_agent",
    ],
  }


def test_extract_supervisor_result_with_trace_dedupes_duplicate_specialist_results():
  result, execution = extract_supervisor_result_with_trace({
    "messages": [
      FakeAgentMessage(
        "tool",
        '{"agent": "lookup_agent", "success": true, "result": {"success": true, "handler": "simple_lookup", "query_type": "location", "criteria": {"target_name": "잠실엘스"}}}',
      ),
      FakeAgentMessage(
        "tool",
        '{"agent": "lookup_agent", "success": true, "result": {"success": true, "handler": "simple_lookup", "query_type": "location", "criteria": {"target_name": "잠실엘스"}}}',
      ),
    ],
  })

  assert result == {
    "success": True,
    "handler": "simple_lookup",
    "query_type": "location",
    "criteria": {
      "target_name": "잠실엘스",
    },
  }
  assert execution == {
    "path": "specialist_tool",
    "selectedAgent": "lookup_agent",
    "deduplicatedCount": 1,
  }


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
  supervisor_message = supervisor.supervisor.payloads[0]["messages"][0]["content"]
  assert "라우팅 참고" in supervisor_message
  assert "recommendation_agent" in supervisor_message
  assert "legal_contract_agent" in supervisor_message


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


def test_extract_agent_result_unwraps_duplicate_tool_results_after_dedupe():
  result = extract_agent_result({
    "messages": [
      FakeAgentMessage(
        "tool",
        '{"success": true, "handler": "simple_lookup", "query_type": "location", "criteria": {"target_name": "잠실엘스"}}',
      ),
      FakeAgentMessage(
        "tool",
        '{"success": true, "handler": "simple_lookup", "query_type": "location", "criteria": {"target_name": "잠실엘스"}}',
      ),
    ],
  })

  assert result == {
    "success": True,
    "handler": "simple_lookup",
    "query_type": "location",
    "criteria": {
      "target_name": "잠실엘스",
    },
  }


def test_extract_agent_result_preserves_nested_partial_success_for_tool_results():
  result = extract_agent_result({
    "messages": [
      FakeAgentMessage("tool", '{"success": true, "handler": "simple_lookup"}'),
      FakeAgentMessage(
        "tool",
        (
          '{"success": true, "status": "partial_success", '
          '"message": "일부 조회 결과만 처리했습니다.", '
          '"results": ['
          '{"success": true, "handler": "simple_lookup"}, '
          '{"success": false, "reason": "no_result"}'
          ']}'
        ),
      ),
    ],
  })

  assert result == {
    "success": True,
    "status": "partial_success",
    "message": "일부 조회 결과만 처리했습니다.",
    "results": [
      {"success": True, "handler": "simple_lookup"},
      {
        "success": True,
        "status": "partial_success",
        "message": "일부 조회 결과만 처리했습니다.",
        "results": [
          {"success": True, "handler": "simple_lookup"},
          {"success": False, "reason": "no_result"},
        ],
      },
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


def test_extract_agent_result_marks_partial_success_for_mixed_parse_failure():
  result = extract_agent_result({
    "messages": [
      FakeAgentMessage("tool", '{"success": true, "handler": "simple_lookup"}'),
      FakeAgentMessage("tool", "not json"),
    ],
  })

  assert result == {
    "success": True,
    "status": "partial_success",
    "message": "일부 조회 결과만 처리했습니다.",
    "results": [
      {"success": True, "handler": "simple_lookup"},
      {
        "success": False,
        "reason": "tool_result_parse_failed",
        "message": "조회 결과를 해석하지 못했습니다. 잠시 후 다시 시도해 주세요.",
      },
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
