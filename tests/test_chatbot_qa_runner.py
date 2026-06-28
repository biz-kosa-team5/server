from pathlib import Path

from scripts.run_chatbot_qa import (
  handler_options_from_text,
  load_cases_from_questionnaire,
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
