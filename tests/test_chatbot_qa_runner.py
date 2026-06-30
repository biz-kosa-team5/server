from pathlib import Path

from scripts.run_chatbot_qa import (
  QaCase,
  QaResult,
  collect_handlers,
  collect_token_check,
  handler_options_from_text,
  load_cases_from_questionnaire,
  render_markdown,
  result_notes,
  run_cases,
)


def test_handler_options_parse_or_and_multi_handler_expectations():
  assert handler_options_from_text("no_matching_tool 또는 recommendation") == (
    ("no_matching_tool",),
    ("recommendation",),
  )
  assert handler_options_from_text("simple_lookup + legal_contract") == (
    ("simple_lookup", "legal_contract"),
  )


def test_load_cases_from_questionnaire_parses_simple_and_mixed_tables(tmp_path: Path):
  questionnaire = tmp_path / "chatbot-questionnaire.md"
  questionnaire.write_text(
    """
| id | check | question | expected_handler | source |
|---|---|---|---|---|
| SL-001 | [ ] | 잠실엘스 위치 알려줘 | simple_lookup | test |
| SL-002 | [ ] | 잠실엘스 시세 알려줘 | simple_lookup + price_trend | test |

| id | check | question | expected_plan_type | expected_execution_path | expected_agents | expected_handlers | expected_dependency | expected_dedupe | answer_checks |
|---|---|---|---|---|---|---|---|---|---|
| MX-ST-001 | [ ] | 강남구 시세추이랑 송파구 시세추이 알려줘 | same_tool_multi_feature | direct_same_tool_features | price_trend_agent, price_trend_agent | price_trend, price_trend | 없음 | 없음 | 지역별 구분 |
""",
    encoding="utf-8",
  )

  cases = load_cases_from_questionnaire(questionnaire)

  assert [case.id for case in cases] == ["SL-001", "SL-002", "MX-ST-001"]
  assert cases[0].expected_handler_options == (("simple_lookup",),)
  assert cases[0].expected_plan_types == ("single_feature",)
  assert cases[1].expected_handler_options == (("simple_lookup", "price_trend"),)
  assert cases[1].expected_plan_types == ("ambiguous_multi_feature",)
  assert cases[2].expected_plan_types == ("same_tool_multi_feature",)
  assert cases[2].expected_handler_options == (("price_trend", "price_trend"),)


def test_load_cases_from_questionnaire_parses_complex_88_schema(tmp_path: Path):
  questionnaire = tmp_path / "chatbot-complex-questionnaire.md"
  questionnaire.write_text(
    """
| id | group | variant | question | expected_plan_type | expected_execution_path | expected_handlers | expected_status | answer_must_include | answer_must_not_include | legal_required | legal_must_include | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MX-001 | comparison_legal | A | 래미안대치팰리스랑 잠실엘스 비교하고 계약금 해제 알려줘 | independent_multi_feature | direct_independent_features | comparison + legal_contract | success;partial_success | 래미안대치팰리스;잠실엘스 | handler;agent | Y | 민법;제565조;계약금;해제 | hard gate |
""",
    encoding="utf-8",
  )

  cases = load_cases_from_questionnaire(questionnaire)

  assert len(cases) == 1
  case = cases[0]
  assert case.id == "MX-001"
  assert case.group == "comparison_legal"
  assert case.variant == "A"
  assert case.expected_handler_options == (("comparison", "legal_contract"),)
  assert case.expected_status == ("success", "partial_success")
  assert case.expected_answer_terms == ("래미안대치팰리스", "잠실엘스")
  assert case.answer_must_not_include == ("handler", "agent")
  assert case.legal_required is True
  assert case.legal_must_include == ("민법", "제565조", "계약금", "해제")


def test_render_markdown_includes_runtime_token_and_full_answer():
  markdown = render_markdown([
    QaResult(
      run_date="2026-06-30",
      id="SL-001",
      test_package="chatbot.qa.specialist_tool.lookup",
      tier="regression",
      question="잠실엘스 위치 알려줘",
      expected_plan_type="single_feature",
      expected_execution_path="specialist_tool",
      expected_handlers=["simple_lookup"],
      expected_handler_options=[["simple_lookup"]],
      expected_status=["success"],
      actual_plan_types=["single_feature"],
      actual_execution_path="specialist_tool",
      actual_agents=["lookup_agent"],
      actual_handlers=["simple_lookup"],
      actual_status="success",
      elapsed_ms=1234,
      token_check="prompt=10, completion=20, total=30",
      answer_ok=True,
      answer="잠실엘스는 잠실동에 있는 단지입니다.\n지도에 표시했습니다.",
      answer_excerpt="잠실엘스는 잠실동에 있는 단지입니다.",
      nested_answer_absent=True,
      passed=True,
      notes="",
      payload={},
    )
  ], live_llm=True)

  assert "| id | package | status | expected path | actual path | expected handlers | actual handlers | elapsed ms | token check | answer ok | nested answer absent | answer | notes |" in markdown
  assert "1234" in markdown
  assert "prompt=10, completion=20, total=30" in markdown
  assert "잠실엘스는 잠실동에 있는 단지입니다.<br>지도에 표시했습니다." in markdown
  assert "## Full Answers" in markdown
  assert "지도에 표시했습니다." in markdown


def test_render_markdown_shows_expected_handler_alternatives():
  markdown = render_markdown([
    QaResult(
      run_date="2026-06-30",
      id="UB-002",
      test_package="chatbot.qa.known_gap.boundary",
      tier="boundary",
      question="부동산 후보 알려줘",
      expected_plan_type="unsupported_feature",
      expected_execution_path="direct_no_matching_tool",
      expected_handlers=["no_matching_tool"],
      expected_handler_options=[["no_matching_tool"], ["recommendation"]],
      expected_status=["success", "partial_success", "failed"],
      actual_plan_types=["single_feature"],
      actual_execution_path="specialist_tool",
      actual_agents=["recommendation_agent"],
      actual_handlers=["recommendation"],
      actual_status="success",
      elapsed_ms=2000,
      token_check="not_captured",
      answer_ok=True,
      answer="추천 후보를 확인했습니다.",
      answer_excerpt="추천 후보를 확인했습니다.",
      nested_answer_absent=True,
      passed=True,
    )
  ], live_llm=True)

  assert "no_matching_tool 또는 recommendation" in markdown


def test_collect_token_check_reads_common_usage_metadata_shapes():
  assert collect_token_check({
    "usage_metadata": {
      "input_tokens": 11,
      "output_tokens": 22,
      "total_tokens": 33,
    }
  }) == "prompt=11, completion=22, total=33"
  assert collect_token_check({"result": {"success": True}}) == "not_captured"


def test_result_notes_accepts_supervisor_first_path_when_handlers_match():
  case = QaCase(
    id="SL-001",
    test_package="chatbot.qa.specialist_tool.lookup",
    question="잠실엘스 위치 알려줘",
    expected_plan_type="single_feature",
    expected_execution_path="direct_feature",
    expected_handlers=("simple_lookup",),
  )

  notes = result_notes(
    case,
    {
      "status": "success",
      "fragments": [
        {
          "execution": {
            "path": "specialist_tool",
            "planType": "single_feature",
            "handler": "simple_lookup",
          }
        }
      ],
    },
    ["single_feature"],
    "specialist_tool",
    ["simple_lookup"],
    True,
    True,
  )

  assert notes == []


def test_result_notes_rejects_nested_answer_and_missing_legal_sources():
  case = QaCase(
    id="MX-001",
    test_package="chatbot.qa.complex.comparison_legal",
    question="래미안대치팰리스랑 잠실엘스 비교하고 계약금 해제 알려줘",
    expected_plan_type="independent_multi_feature",
    expected_execution_path="direct_independent_features",
    expected_handlers=("comparison", "legal_contract"),
    expected_status=("success", "partial_success"),
    expected_answer_terms=("래미안대치팰리스", "잠실엘스"),
    legal_required=True,
    legal_must_include=("민법", "제565조", "계약금", "해제"),
  )
  payload = {
    "status": "success",
    "answer": "래미안대치팰리스와 잠실엘스 비교입니다. 민법 제565조 계약금 해제 규정입니다.",
    "result": {"answer": "nested", "handler": "legal_contract", "success": False, "sources": []},
    "fragments": [
      {"execution": {"path": "direct_independent_features", "planType": "independent_multi_feature", "handlerCalls": ["comparison", "legal_contract"]}}
    ],
  }

  notes = result_notes(
    case,
    payload,
    ["independent_multi_feature"],
    "direct_independent_features",
    ["comparison", "legal_contract"],
    True,
    False,
  )

  assert "nested answer found" in notes
  assert "legal_required expected legal result success=true" in notes
  assert "legal_required expected at least one legal source" in notes


def test_result_notes_accepts_legal_success_with_sources():
  case = QaCase(
    id="MX-001",
    test_package="chatbot.qa.complex.comparison_legal",
    question="계약금 해제",
    expected_plan_type="independent_multi_feature",
    expected_execution_path="direct_independent_features",
    expected_handlers=("comparison", "legal_contract"),
    expected_status=("success", "partial_success"),
    expected_answer_terms=("민법",),
    legal_required=True,
    legal_must_include=("민법", "제565조", "계약금", "해제"),
  )
  payload = {
    "status": "success",
    "answer": "민법 제565조에 따라 계약금 해제를 설명합니다.",
    "result": {"handler": "legal_contract", "success": True, "sources": [{"title": "민법"}]},
    "fragments": [
      {"execution": {"path": "direct_independent_features", "planType": "independent_multi_feature", "handlerCalls": ["comparison", "legal_contract"]}}
    ],
  }

  notes = result_notes(
    case,
    payload,
    ["independent_multi_feature"],
    "direct_independent_features",
    ["comparison", "legal_contract"],
    True,
    True,
  )

  assert notes == []


def test_run_cases_live_http_fail_fast_legal(monkeypatch):
  case = QaCase(
    id="MX-001",
    test_package="chatbot.qa.complex.lookup_legal",
    question="잠실엘스와 계약금 해제",
    expected_plan_type="independent_multi_feature",
    expected_execution_path="direct_independent_features",
    expected_handlers=("simple_lookup", "legal_contract"),
    expected_status=("success", "partial_success"),
    legal_required=True,
    legal_must_include=("민법", "제565조", "계약금", "해제"),
  )

  async def fake_post_chatbot_query(_base_url: str, _question: str):
    return {
      "__http_status": 200,
      "status": "success",
      "answer": "잠실엘스 답변입니다.",
      "fragments": [
        {"execution": {"path": "direct_independent_features", "planType": "independent_multi_feature", "handlerCalls": ["simple_lookup"]}}
      ],
    }

  monkeypatch.setattr("scripts.run_chatbot_qa.post_chatbot_query", fake_post_chatbot_query)

  results = __import__("asyncio").run(run_cases(
    None,
    (case, case),
    "2026-06-30",
    strict_supervisor_first=False,
    live_http=True,
    fail_fast_legal=True,
  ))

  assert len(results) == 1
  assert results[0].legal_fail_fast_triggered is True
  assert "legal_required expected legal_contract handler" in results[0].notes


def test_result_notes_rejects_direct_path_in_strict_supervisor_first_mode():
  case = QaCase(
    id="SL-001",
    test_package="chatbot.qa.specialist_tool.lookup",
    question="잠실엘스 위치 알려줘",
    expected_plan_type="single_feature",
    expected_execution_path="direct_feature",
    expected_handlers=("simple_lookup",),
  )

  notes = result_notes(
    case,
    {
      "status": "success",
      "fragments": [
        {
          "execution": {
            "path": "direct_feature",
            "planType": "single_feature",
            "handler": "simple_lookup",
            "fallbackFrom": "supervisor",
            "fallbackReason": "supervisor_no_tool",
          }
        }
      ],
    },
    ["single_feature"],
    "direct_feature",
    ["simple_lookup"],
    True,
    True,
    strict_supervisor_first=True,
  )

  assert "path expected one of ('direct_feature',), got direct_feature" in notes


def test_result_notes_accepts_supported_alternative_with_no_matching_option_in_strict_mode():
  case = QaCase(
    id="UB-002",
    test_package="chatbot.qa.known_gap.boundary",
    question="부동산 후보 알려줘",
    expected_plan_type="unsupported_feature",
    expected_execution_path="direct_no_matching_tool",
    expected_handlers=("no_matching_tool",),
    expected_plan_types=("unsupported_feature", "single_feature"),
    expected_execution_paths=("direct_no_matching_tool", "supervisor_no_tool", "direct_feature"),
    expected_handler_options=(("no_matching_tool",), ("recommendation",)),
    expected_status=("success", "partial_success", "failed"),
  )

  notes = result_notes(
    case,
    {
      "status": "success",
      "fragments": [
        {
          "execution": {
            "path": "specialist_tool",
            "planType": "single_feature",
            "handler": "recommendation",
          }
        }
      ],
    },
    ["single_feature"],
    "specialist_tool",
    ["recommendation"],
    True,
    True,
    strict_supervisor_first=True,
  )

  assert notes == []


def test_collect_handlers_prefers_handler_calls_to_preserve_duplicates():
  assert collect_handlers({
    "fragments": [
      {
        "execution": {
          "path": "supervisor_aggregate",
          "handlers": ["price_trend"],
          "handlerCalls": ["price_trend", "price_trend"],
        }
      }
    ]
  }) == ["price_trend", "price_trend"]
