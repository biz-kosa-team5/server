from scripts.run_chatbot_model_eval import (
  ALLOWED_MODELS,
  DEFAULT_MODEL_PRICES,
  EvalResult,
  MODEL_EVAL_CASES,
  MODEL_EVAL_RUN_GROUPS,
  estimate_cost,
  expected_handlers_present,
  normalize_token_usage,
  render_markdown,
  token_field_values,
)


def test_model_eval_matrix_is_fixed_to_20_cases_and_4_run_groups():
  assert len(MODEL_EVAL_CASES) == 20
  assert len(MODEL_EVAL_RUN_GROUPS) == 4
  assert {group.model_id for group in MODEL_EVAL_RUN_GROUPS} == set(ALLOWED_MODELS)
  assert {group.name for group in MODEL_EVAL_RUN_GROUPS} == {
    "project-gpt-5.5",
    "project-gpt-5.4-mini",
    "raw-gpt-5.5",
    "raw-gpt-5.4-mini",
  }


def test_expected_handlers_match_detailed_handler_labels():
  assert expected_handlers_present(
    ("simple_lookup", "price_trend"),
    ["simple_lookup.trade_history", "price_trend.timeseries"],
  )
  assert not expected_handlers_present(
    ("comparison", "legal_contract"),
    ["comparison"],
  )


def test_token_usage_and_cost_include_cached_tokens():
  usage = normalize_token_usage({
    "input_tokens": 1000,
    "output_tokens": 200,
    "cached_tokens": 400,
    "total_tokens": 1200,
  })

  assert usage == {
    "input_tokens": 1000,
    "output_tokens": 200,
    "cached_tokens": 400,
    "total_tokens": 1200,
  }
  assert estimate_cost(usage, "gpt-5.5", DEFAULT_MODEL_PRICES) == 0.0028


def test_missing_usage_fields_are_marked_measurement_failed():
  assert token_field_values(None) == {
    "input_tokens": "measurement_failed",
    "output_tokens": "measurement_failed",
    "cached_tokens": "measurement_failed",
    "total_tokens": "measurement_failed",
  }


def test_render_markdown_uses_korean_columns_and_full_answer_blocks():
  markdown = render_markdown([
    EvalResult(
      run_date="2026-06-30",
      case_id="SL-001",
      category="simple_lookup",
      question="잠실엘스 위치 알려줘",
      run_group="project-gpt-5.5",
      model_id="gpt-5.5",
      status="success",
      expected_path="specialist_tool",
      actual_path="specialist_tool",
      expected_handlers=["simple_lookup"],
      actual_handlers=["simple_lookup.location"],
      tool_called=True,
      fallback_used=False,
      answer_ok=True,
      answer_fidelity="충실",
      quality_note="정상",
      elapsed_ms=1234,
      input_tokens=100,
      output_tokens=50,
      cached_tokens=0,
      total_tokens=150,
      estimated_cost_usd=0.000625,
      answer_length=18,
      answer_ref="answer-001",
      answer="잠실엘스는 잠실동에 있습니다.",
    )
  ])

  assert "| 문항 ID | 분류 | 질문 | 실행군 | 모델 ID | 상태 | 기대 경로 | 실제 경로 | 기대 핸들러 | 실제 핸들러 |" in markdown
  assert "### <a id=\"answer-001\"></a>SL-001 / project-gpt-5.5" in markdown
  assert "```text\n잠실엘스는 잠실동에 있습니다.\n```" in markdown
