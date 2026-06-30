from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from openai import OpenAI


SERVER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVER_ROOT.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "qa"
SUITE_NAME = "chatbot-model-eval"
ALLOWED_MODELS = ("gpt-5.5", "gpt-5.4-mini")
DEFAULT_ROW_TIMEOUT_SECONDS = 180.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True)
class TokenPrices:
  input_per_1m: float
  output_per_1m: float
  cached_input_per_1m: float


DEFAULT_MODEL_PRICES = {
  "gpt-5.5": TokenPrices(input_per_1m=1.25, output_per_1m=10.0, cached_input_per_1m=0.125),
  "gpt-5.4-mini": TokenPrices(input_per_1m=0.25, output_per_1m=2.0, cached_input_per_1m=0.025),
}


@dataclass(frozen=True)
class EvalCase:
  id: str
  category: str
  question: str
  expected_handlers: tuple[str, ...]
  expected_project_path: str
  kind: Literal["single", "multi", "exception"] = "single"


@dataclass(frozen=True)
class RunGroup:
  name: str
  model_id: str
  mode: Literal["project", "raw"]


@dataclass
class EvalResult:
  run_date: str
  case_id: str
  category: str
  question: str
  run_group: str
  model_id: str
  status: str
  expected_path: str
  actual_path: str
  expected_handlers: list[str]
  actual_handlers: list[str]
  tool_called: bool
  fallback_used: bool
  answer_ok: bool
  answer_fidelity: str
  quality_note: str
  elapsed_ms: int | str
  input_tokens: int | str
  output_tokens: int | str
  cached_tokens: int | str
  total_tokens: int | str
  estimated_cost_usd: float | str
  answer_length: int
  answer_ref: str
  notes: str = ""
  answer: str = ""
  actual_tools: list[str] = field(default_factory=list)
  usage: dict[str, int] | None = None
  handler_trace: dict[str, Any] = field(default_factory=dict)
  evaluation: dict[str, Any] = field(default_factory=dict)
  raw_response: Any = None


MODEL_EVAL_CASES: tuple[EvalCase, ...] = (
  EvalCase("SL-001", "simple_lookup", "잠실엘스 위치 알려줘", ("simple_lookup",), "specialist_tool"),
  EvalCase("SL-002", "simple_lookup", "잠실엘스 최근 실거래 알려줘", ("simple_lookup",), "specialist_tool"),
  EvalCase("SL-003", "simple_lookup", "은마 아파트 정보를 줘봐", ("simple_lookup",), "specialist_tool"),
  EvalCase("RC-001", "recommendation", "강남구 아파트 추천해줘", ("recommendation",), "specialist_tool"),
  EvalCase("RC-002", "recommendation", "송파구 30억 이하 아파트 추천해줘", ("recommendation",), "specialist_tool"),
  EvalCase("RC-003", "recommendation", "초등학교 근처 아파트 추천해줘", ("recommendation",), "specialist_tool"),
  EvalCase("CP-001", "comparison", "래미안대치팰리스랑 잠실엘스 가격 비교해줘", ("comparison",), "specialist_tool"),
  EvalCase("CP-002", "comparison", "래미안대치팰리스랑 압구정현대 가격 비교해줘", ("comparison",), "specialist_tool"),
  EvalCase("CP-003", "comparison", "동부썬빌이랑 두산위브 가격이랑 학교 거리 비교해줘", ("comparison",), "specialist_tool"),
  EvalCase("TR-001", "price_trend", "잠실엘스 최근 1년 가격 흐름 알려줘", ("price_trend",), "specialist_tool"),
  EvalCase("TR-002", "price_trend", "강남구 최근 1년 가격 흐름 알려줘", ("price_trend",), "specialist_tool"),
  EvalCase("TR-003", "price_trend", "강남구에서 최근 가격 상승률 높은 아파트 알려줘", ("price_trend",), "specialist_tool"),
  EvalCase("LC-001", "legal_contract", "아파트 매매 시 세금 책정 관련 법을 알려줘", ("legal_contract",), "specialist_tool"),
  EvalCase("LC-002", "legal_contract", "계약금을 냈는데 계약을 취소할 수 있어?", ("legal_contract",), "specialist_tool"),
  EvalCase("LC-003", "legal_contract", "부동산 거래 신고는 누가 해야 해?", ("legal_contract",), "specialist_tool"),
  EvalCase("MX-001", "mixed", "강남구 아파트 추천하고 최근 1년 가격 흐름도 알려줘", ("recommendation", "price_trend"), "supervisor_aggregate", "multi"),
  EvalCase("MX-002", "mixed", "강남구 아파트 추천하고 후보 비교도 해줘", ("recommendation", "comparison"), "supervisor_aggregate", "multi"),
  EvalCase("MX-003", "mixed", "래미안대치팰리스랑 잠실엘스 비교하고 계약금 해제도 알려줘", ("comparison", "legal_contract"), "supervisor_aggregate", "multi"),
  EvalCase("EX-001", "exception", "날씨랑 잠실엘스 시세 같이 알려줘", ("price_trend", "no_matching_tool"), "supervisor_aggregate", "exception"),
  EvalCase("EX-002", "exception", "부동산이랑 상관없는 질문인데 오늘 점심 뭐 먹지?", ("no_matching_tool",), "supervisor_no_tool", "exception"),
)


MODEL_EVAL_RUN_GROUPS: tuple[RunGroup, ...] = (
  RunGroup("project-gpt-5.5", "gpt-5.5", "project"),
  RunGroup("project-gpt-5.4-mini", "gpt-5.4-mini", "project"),
  RunGroup("raw-gpt-5.5", "gpt-5.5", "raw"),
  RunGroup("raw-gpt-5.4-mini", "gpt-5.4-mini", "raw"),
)


RAW_SYSTEM_PROMPT = """
한국어로 답변하세요.
모르면 모른다고 답변하세요.
1000자 이내로 답변하세요.
""".strip()

BANNED_ANSWER_TERMS = (
  "handler",
  "agent",
  "tool",
  "execution",
  "planType",
  "fragment",
  "dedupe",
  "selectedAgent",
)


def main() -> int:
  args = parse_args()
  configure_environment()
  from app.config import load_environment
  from app.database import SessionLocal, ensure_initialized

  load_environment()
  selected_cases = filter_cases(MODEL_EVAL_CASES, args.case)
  selected_run_groups = filter_run_groups(MODEL_EVAL_RUN_GROUPS, args.run_group)
  validate_run_matrix(selected_cases, selected_run_groups)

  output_dir = Path(args.output_dir)
  output_dir.mkdir(parents=True, exist_ok=True)
  run_date = datetime.now().strftime("%Y-%m-%d")
  markdown_path = output_dir / f"{SUITE_NAME}-{run_date}.md"
  jsonl_path = output_dir / f"{SUITE_NAME}-{run_date}.jsonl"

  prices = load_model_prices()
  preflight = (
    {"ok": True, "models": []}
    if args.skip_preflight
    else preflight_models(
      tuple(sorted({group.model_id for group in selected_run_groups})),
      timeout_seconds=args.request_timeout_seconds,
    )
  )
  if not preflight["ok"]:
    markdown_path.write_text(render_preflight_failure_markdown(run_date, preflight), encoding="utf-8")
    write_preflight_failure_jsonl(jsonl_path, run_date, preflight)
    print(f"preflight failed; wrote {markdown_path}")
    print(f"preflight failed; wrote {jsonl_path}")
    return 1

  ensure_initialized()
  with SessionLocal() as session:
    results = asyncio.run(run_eval_matrix(
      session,
      selected_cases,
      selected_run_groups,
      run_date,
      prices,
      row_timeout_seconds=args.row_timeout_seconds,
      request_timeout_seconds=args.request_timeout_seconds,
    ))

  markdown_path.write_text(render_markdown(results), encoding="utf-8")
  write_jsonl(jsonl_path, results)

  passed = sum(1 for result in results if result.answer_ok and result.status not in {"failed", "measurement_failed"})
  measurement_failed = sum(1 for result in results if result.status == "measurement_failed")
  print(f"wrote {markdown_path}")
  print(f"wrote {jsonl_path}")
  print(f"model eval summary: total={len(results)} passed={passed} measurement_failed={measurement_failed}")
  if measurement_failed and not args.allow_measurement_failures:
    return 1
  return 0


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description="Run the fixed 80-row chatbot model evaluation.")
  parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
  parser.add_argument("--case", action="append", default=[], help="Run only matching case id. Can be repeated.")
  parser.add_argument("--run-group", action="append", default=[], help="Run only matching run group. Can be repeated.")
  parser.add_argument("--skip-preflight", action="store_true", help="Skip model access preflight. Intended for local test doubles only.")
  parser.add_argument("--allow-measurement-failures", action="store_true", help="Exit 0 even when token usage is missing.")
  parser.add_argument("--row-timeout-seconds", type=float, default=DEFAULT_ROW_TIMEOUT_SECONDS)
  parser.add_argument("--request-timeout-seconds", type=float, default=DEFAULT_REQUEST_TIMEOUT_SECONDS)
  return parser.parse_args()


def configure_environment() -> None:
  if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))
  if os.getenv("CHATBOT_QA_USE_EXISTING_DATABASE") != "1":
    os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
    os.environ.setdefault("DATA_IMPORT_DIR", str(SERVER_ROOT / "db" / "import"))
  import app.chatbot.features.legal_contract.rag.model  # noqa: F401


def filter_cases(cases: tuple[EvalCase, ...], case_ids: list[str]) -> tuple[EvalCase, ...]:
  if not case_ids:
    return cases
  wanted = set(case_ids)
  return tuple(case for case in cases if case.id in wanted)


def filter_run_groups(groups: tuple[RunGroup, ...], names: list[str]) -> tuple[RunGroup, ...]:
  if not names:
    return groups
  wanted = set(names)
  return tuple(group for group in groups if group.name in wanted)


def validate_run_matrix(cases: tuple[EvalCase, ...], groups: tuple[RunGroup, ...]) -> None:
  models = {group.model_id for group in groups}
  disallowed = models - set(ALLOWED_MODELS)
  if disallowed:
    raise SystemExit(f"disallowed model ids: {', '.join(sorted(disallowed))}")
  if not cases:
    raise SystemExit("no evaluation cases selected")
  if not groups:
    raise SystemExit("no run groups selected")


async def run_eval_matrix(
  session: Any,
  cases: tuple[EvalCase, ...],
  run_groups: tuple[RunGroup, ...],
  run_date: str,
  prices: dict[str, TokenPrices],
  *,
  row_timeout_seconds: float,
  request_timeout_seconds: float,
) -> list[EvalResult]:
  results: list[EvalResult] = []
  total = len(cases) * len(run_groups)
  for case in cases:
    for run_group in run_groups:
      answer_ref = f"answer-{len(results) + 1:03d}"
      print(f"[{len(results) + 1}/{total}] {case.id} / {run_group.name}", flush=True)
      started_at = perf_counter()
      try:
        if run_group.mode == "project":
          result = await asyncio.wait_for(
            run_project_case(session, case, run_group, run_date, prices, answer_ref),
            timeout=row_timeout_seconds,
          )
        else:
          result = await asyncio.wait_for(
            run_raw_case(
              case,
              run_group,
              run_date,
              prices,
              answer_ref,
              request_timeout_seconds=request_timeout_seconds,
            ),
            timeout=row_timeout_seconds,
          )
      except TimeoutError:
        result = timeout_eval_result(
          case,
          run_group,
          run_date,
          answer_ref,
          elapsed_ms=round((perf_counter() - started_at) * 1000),
          row_timeout_seconds=row_timeout_seconds,
        )
      results.append(result)
      print(f"  -> {result.status} ({result.elapsed_ms} ms)", flush=True)
  return results


async def run_project_case(
  session: Any,
  case: EvalCase,
  run_group: RunGroup,
  run_date: str,
  prices: dict[str, TokenPrices],
  answer_ref: str,
) -> EvalResult:
  from app.chatbot.service.chatbot_service import handle_chatbot_query

  started_at = perf_counter()
  payload: dict[str, Any]
  try:
    payload = await handle_chatbot_query(session, {
      "question": case.question,
      "model": run_group.model_id,
    })
    elapsed_ms = round((perf_counter() - started_at) * 1000)
  except Exception as exc:
    elapsed_ms = round((perf_counter() - started_at) * 1000)
    payload = {
      "success": False,
      "status": "failed",
      "answer": "",
      "error": {
        "type": exc.__class__.__name__,
        "message": str(exc),
      },
    }

  answer = payload.get("answer") if isinstance(payload.get("answer"), str) else ""
  usage = normalize_token_usage(payload.get("usage"))
  actual_handlers = collect_actual_handlers(payload)
  actual_path = collect_actual_path(payload)
  fallback_used = project_fallback_used(payload)
  tool_called = project_tool_called(payload, actual_handlers)
  answer_ok, fidelity, quality_note, eval_notes = evaluate_project_answer(
    case,
    answer,
    actual_handlers,
    actual_path,
    tool_called,
  )
  status = result_status(payload, answer_ok, usage)
  token_fields = token_field_values(usage)
  cost = estimate_cost(usage, run_group.model_id, prices) if usage else "measurement_failed"

  return EvalResult(
    run_date=run_date,
    case_id=case.id,
    category=case.category,
    question=case.question,
    run_group=run_group.name,
    model_id=run_group.model_id,
    status=status,
    expected_path=case.expected_project_path,
    actual_path=actual_path or "-",
    expected_handlers=list(case.expected_handlers),
    actual_handlers=actual_handlers,
    tool_called=tool_called,
    fallback_used=fallback_used,
    answer_ok=answer_ok,
    answer_fidelity=fidelity,
    quality_note=quality_note,
    elapsed_ms=elapsed_ms,
    input_tokens=token_fields["input_tokens"],
    output_tokens=token_fields["output_tokens"],
    cached_tokens=token_fields["cached_tokens"],
    total_tokens=token_fields["total_tokens"],
    estimated_cost_usd=cost,
    answer_length=len(answer),
    answer_ref=answer_ref,
    notes="; ".join(eval_notes),
    answer=answer,
    actual_tools=collect_actual_tools(payload),
    usage=usage,
    handler_trace=collect_handler_trace(payload),
    evaluation={
      "expected_handlers_present": expected_handlers_present(case.expected_handlers, actual_handlers),
      "missing_handlers": missing_handlers(case.expected_handlers, actual_handlers),
      "raw_payload_status": payload.get("status"),
    },
    raw_response=payload,
  )


async def run_raw_case(
  case: EvalCase,
  run_group: RunGroup,
  run_date: str,
  prices: dict[str, TokenPrices],
  answer_ref: str,
  *,
  request_timeout_seconds: float,
) -> EvalResult:
  from app.chatbot.service.answer.composer import extract_response_content, extract_usage_metadata

  started_at = perf_counter()
  raw_response: Any = None
  error: dict[str, str] | None = None
  try:
    client = OpenAI(
      api_key=resolve_openai_api_key(),
      timeout=request_timeout_seconds,
    )
    raw_response = await asyncio.wait_for(
      asyncio.to_thread(
        client.chat.completions.create,
        model=run_group.model_id,
        max_completion_tokens=700,
        messages=[
          {"role": "system", "content": RAW_SYSTEM_PROMPT},
          {"role": "user", "content": case.question},
        ],
      ),
      timeout=request_timeout_seconds + 5,
    )
    answer = extract_response_content(raw_response)
    usage = extract_usage_metadata(raw_response)
  except Exception as exc:
    answer = ""
    usage = None
    error = {
      "type": exc.__class__.__name__,
      "message": str(exc),
    }
  elapsed_ms = round((perf_counter() - started_at) * 1000)

  answer_ok, fidelity, quality_note, eval_notes = evaluate_raw_answer(answer)
  status = "measurement_failed" if usage is None else ("success" if answer_ok else "failed")
  token_fields = token_field_values(usage)
  cost = estimate_cost(usage, run_group.model_id, prices) if usage else "measurement_failed"

  return EvalResult(
    run_date=run_date,
    case_id=case.id,
    category=case.category,
    question=case.question,
    run_group=run_group.name,
    model_id=run_group.model_id,
    status=status,
    expected_path="raw_model",
    actual_path="raw_model" if error is None else "raw_model_failed",
    expected_handlers=[],
    actual_handlers=[],
    tool_called=False,
    fallback_used=False,
    answer_ok=answer_ok,
    answer_fidelity=fidelity,
    quality_note=quality_note,
    elapsed_ms=elapsed_ms,
    input_tokens=token_fields["input_tokens"],
    output_tokens=token_fields["output_tokens"],
    cached_tokens=token_fields["cached_tokens"],
    total_tokens=token_fields["total_tokens"],
    estimated_cost_usd=cost,
    answer_length=len(answer),
    answer_ref=answer_ref,
    notes="; ".join(eval_notes),
    answer=answer,
    usage=usage,
    handler_trace={},
    evaluation={
      "raw_tool_absent": True,
      "error": error,
    },
    raw_response=serialize_openai_response(raw_response) if raw_response is not None else {"error": error},
  )


def evaluate_project_answer(
  case: EvalCase,
  answer: str,
  actual_handlers: list[str],
  actual_path: str,
  tool_called: bool,
) -> tuple[bool, str, str, list[str]]:
  notes = []
  if not answer.strip():
    notes.append("답변이 비어 있음")
  if any(term in answer for term in BANNED_ANSWER_TERMS):
    notes.append("내부 처리 용어가 답변에 노출됨")

  actual_base_handlers = [base_handler(handler) for handler in actual_handlers]
  expected_present = expected_handlers_present(case.expected_handlers, actual_handlers)
  missing = missing_handlers(case.expected_handlers, actual_handlers)
  if case.kind == "multi":
    if not expected_present:
      notes.append(f"복합 handler 누락: {', '.join(missing)}")
      fidelity = "부분 성공" if any(handler in actual_base_handlers for handler in case.expected_handlers) else "실패"
    else:
      fidelity = "충실"
  elif case.kind == "exception":
    fidelity = exception_fidelity(case, answer, actual_base_handlers, actual_path)
    if fidelity == "실패":
      notes.append("예외 질문 처리 기준 미충족")
  else:
    if not expected_present:
      notes.append(f"기대 handler 누락: {', '.join(missing)}")
      fidelity = "실패"
    else:
      fidelity = "충실"

  if case.kind != "exception" and not tool_called:
    notes.append("데이터 기반 질문인데 tool 호출 흔적 없음")

  answer_ok = not notes
  quality_note = "정상" if answer_ok else "; ".join(notes)
  if "direct" in actual_path or "fallback" in actual_path:
    quality_note = f"{quality_note}; fallback/direct 확인 필요"
  return answer_ok, fidelity, quality_note, notes


def exception_fidelity(case: EvalCase, answer: str, actual_base_handlers: list[str], actual_path: str) -> str:
  if case.id == "EX-001":
    has_supported_part = any(handler in actual_base_handlers for handler in ("simple_lookup", "price_trend"))
    explains_weather_limit = "날씨" in answer and any(term in answer for term in ("지원", "확인", "제공된", "처리"))
    return "충실" if has_supported_part and explains_weather_limit else "부분 성공"
  if case.id == "EX-002":
    unsupported_path = "no_tool" in actual_path or "no_matching_tool" in ",".join(actual_base_handlers)
    scope_text = any(term in answer for term in ("지원", "부동산", "처리", "질문"))
    return "충실" if unsupported_path and scope_text else "부분 성공"
  return "부분 성공"


def evaluate_raw_answer(answer: str) -> tuple[bool, str, str, list[str]]:
  notes = []
  if not answer.strip():
    notes.append("답변이 비어 있음")
  if len(answer) > 1200:
    notes.append("raw 답변이 길이 기준을 크게 초과")
  answer_ok = not notes
  if answer_ok:
    return True, "참고용", "tool 없는 순수 모델 답변이라 데이터 정확도는 별도 검토 필요", []
  return False, "실패", "; ".join(notes), notes


def result_status(payload: dict[str, Any], answer_ok: bool, usage: dict[str, int] | None) -> str:
  if usage is None:
    return "measurement_failed"
  raw_status = str(payload.get("status") or "")
  if raw_status in {"success", "partial_success", "failed"}:
    return raw_status if answer_ok else "failed"
  return "success" if answer_ok else "failed"


def timeout_eval_result(
  case: EvalCase,
  run_group: RunGroup,
  run_date: str,
  answer_ref: str,
  *,
  elapsed_ms: int,
  row_timeout_seconds: float,
) -> EvalResult:
  token_fields = token_field_values(None)
  note = f"row timeout after {row_timeout_seconds:g}s"
  return EvalResult(
    run_date=run_date,
    case_id=case.id,
    category=case.category,
    question=case.question,
    run_group=run_group.name,
    model_id=run_group.model_id,
    status="measurement_failed",
    expected_path=case.expected_project_path if run_group.mode == "project" else "raw_model",
    actual_path=f"{run_group.mode}_timeout",
    expected_handlers=list(case.expected_handlers) if run_group.mode == "project" else [],
    actual_handlers=[],
    tool_called=False,
    fallback_used=False,
    answer_ok=False,
    answer_fidelity="실패",
    quality_note=note,
    elapsed_ms=elapsed_ms,
    input_tokens=token_fields["input_tokens"],
    output_tokens=token_fields["output_tokens"],
    cached_tokens=token_fields["cached_tokens"],
    total_tokens=token_fields["total_tokens"],
    estimated_cost_usd="measurement_failed",
    answer_length=0,
    answer_ref=answer_ref,
    notes=note,
    answer="",
    usage=None,
    handler_trace={},
    evaluation={"timeout": True, "row_timeout_seconds": row_timeout_seconds},
    raw_response={"error": {"type": "TimeoutError", "message": note}},
  )


def collect_actual_handlers(payload: dict[str, Any]) -> list[str]:
  detailed = collect_detailed_result_handlers(payload.get("result"))
  if detailed:
    return detailed

  handlers = []
  for execution in fragment_executions(payload):
    handler_calls = execution.get("handlerCalls")
    if isinstance(handler_calls, list):
      handlers.extend(str(handler) for handler in handler_calls)
      continue
    execution_handlers = execution.get("handlers")
    if isinstance(execution_handlers, list):
      handlers.extend(str(handler) for handler in execution_handlers)
      continue
    handler = execution.get("handler")
    if isinstance(handler, str):
      handlers.append(handler)
  return handlers


def collect_detailed_result_handlers(value: Any) -> list[str]:
  handlers: list[str] = []

  def visit(item: Any) -> None:
    if isinstance(item, list):
      for child in item:
        visit(child)
      return
    if not isinstance(item, dict):
      return
    handler = item.get("handler")
    if isinstance(handler, str):
      handlers.append(detailed_handler_label(handler, item))
    nested = item.get("result")
    if nested is not None:
      visit(nested)
    nested_results = item.get("results")
    if nested_results is not None:
      visit(nested_results)

  visit(value)
  return handlers


def detailed_handler_label(handler: str, result: dict[str, Any]) -> str:
  criteria = result.get("criteria") if isinstance(result.get("criteria"), dict) else {}
  if handler == "simple_lookup":
    query_type = result.get("query_type") or criteria.get("query_type")
    return f"{handler}.{query_type}" if query_type else handler
  if handler == "price_trend":
    analysis_type = result.get("analysis_type") or criteria.get("analysis_type") or result.get("observation_type")
    return f"{handler}.{analysis_type}" if analysis_type else handler
  return handler


def collect_actual_path(payload: dict[str, Any]) -> str:
  paths = [
    str(execution.get("path"))
    for execution in fragment_executions(payload)
    if execution.get("path")
  ]
  return ",".join(paths)


def collect_actual_tools(payload: dict[str, Any]) -> list[str]:
  tools: list[str] = []
  for execution in fragment_executions(payload):
    for key in ("selectedAgent", "handler"):
      value = execution.get(key)
      if isinstance(value, str) and value not in tools:
        tools.append(value)
    for key in ("selectedAgents", "handlers", "handlerCalls"):
      value = execution.get(key)
      if isinstance(value, list):
        for item in value:
          name = str(item)
          if name not in tools:
            tools.append(name)
    for trace in execution.get("specialistTraces", []) if isinstance(execution.get("specialistTraces"), list) else []:
      if not isinstance(trace, dict):
        continue
      for tool_name in trace.get("toolCalls", []):
        name = str(tool_name)
        if name not in tools:
          tools.append(name)
  return tools


def collect_handler_trace(payload: dict[str, Any]) -> dict[str, Any]:
  return {
    "fragments": [
      {
        "index": fragment.get("index"),
        "text": fragment.get("text"),
        "execution": fragment.get("execution"),
      }
      for fragment in payload.get("fragments", [])
      if isinstance(fragment, dict)
    ],
    "uiActions": payload.get("uiActions", []),
    "uiArtifacts": payload.get("uiArtifacts", []),
    "uiSummary": payload.get("uiSummary"),
  }


def fragment_executions(payload: dict[str, Any]) -> list[dict[str, Any]]:
  fragments = payload.get("fragments")
  if not isinstance(fragments, list):
    return []
  executions = []
  for fragment in fragments:
    if not isinstance(fragment, dict):
      continue
    execution = fragment.get("execution")
    if isinstance(execution, dict):
      executions.append(execution)
  return executions


def project_tool_called(payload: dict[str, Any], actual_handlers: list[str]) -> bool:
  paths = set(filter(None, collect_actual_path(payload).split(",")))
  if paths & {"specialist_tool", "supervisor_aggregate"}:
    return True
  return any(base_handler(handler) not in {"no_matching_tool"} for handler in actual_handlers)


def project_fallback_used(payload: dict[str, Any]) -> bool:
  for execution in fragment_executions(payload):
    if execution.get("fallbackFrom") or execution.get("fallbackReason"):
      return True
    path = str(execution.get("path") or "")
    if path.startswith("direct_") or path == "direct_feature":
      return True
  return False


def expected_handlers_present(expected_handlers: tuple[str, ...], actual_handlers: list[str]) -> bool:
  actual_counts: dict[str, int] = {}
  for handler in actual_handlers:
    base = base_handler(handler)
    actual_counts[base] = actual_counts.get(base, 0) + 1
  for expected in expected_handlers:
    base = base_handler(expected)
    if actual_counts.get(base, 0) <= 0:
      return False
    actual_counts[base] -= 1
  return True


def missing_handlers(expected_handlers: tuple[str, ...], actual_handlers: list[str]) -> list[str]:
  actual_counts: dict[str, int] = {}
  for handler in actual_handlers:
    base = base_handler(handler)
    actual_counts[base] = actual_counts.get(base, 0) + 1
  missing = []
  for expected in expected_handlers:
    base = base_handler(expected)
    if actual_counts.get(base, 0) <= 0:
      missing.append(expected)
    else:
      actual_counts[base] -= 1
  return missing


def base_handler(handler: str) -> str:
  return handler.split(".", 1)[0]


def normalize_token_usage(value: Any) -> dict[str, int] | None:
  if not isinstance(value, dict):
    return None
  input_tokens = int_or_zero(value.get("input_tokens") or value.get("prompt_tokens"))
  output_tokens = int_or_zero(value.get("output_tokens") or value.get("completion_tokens"))
  cached_tokens = int_or_zero(value.get("cached_tokens"))
  total_tokens = int_or_zero(value.get("total_tokens"))
  if total_tokens == 0:
    total_tokens = input_tokens + output_tokens
  if input_tokens == 0 and output_tokens == 0 and cached_tokens == 0 and total_tokens == 0:
    return None
  return {
    "input_tokens": input_tokens,
    "output_tokens": output_tokens,
    "cached_tokens": cached_tokens,
    "total_tokens": total_tokens,
  }


def token_field_values(usage: dict[str, int] | None) -> dict[str, int | str]:
  if usage is None:
    return {
      "input_tokens": "measurement_failed",
      "output_tokens": "measurement_failed",
      "cached_tokens": "measurement_failed",
      "total_tokens": "measurement_failed",
    }
  return {
    "input_tokens": usage["input_tokens"],
    "output_tokens": usage["output_tokens"],
    "cached_tokens": usage["cached_tokens"],
    "total_tokens": usage["total_tokens"],
  }


def estimate_cost(
  usage: dict[str, int] | None,
  model_id: str,
  prices: dict[str, TokenPrices],
) -> float:
  if usage is None:
    return 0.0
  price = prices[model_id]
  cached = min(usage["cached_tokens"], usage["input_tokens"])
  uncached_input = max(0, usage["input_tokens"] - cached)
  cost = (
    uncached_input * price.input_per_1m
    + cached * price.cached_input_per_1m
    + usage["output_tokens"] * price.output_per_1m
  ) / 1_000_000
  return round(cost, 8)


def load_model_prices() -> dict[str, TokenPrices]:
  raw = os.getenv("CHATBOT_MODEL_EVAL_PRICES_JSON", "").strip()
  if not raw:
    return DEFAULT_MODEL_PRICES
  data = json.loads(raw)
  prices = dict(DEFAULT_MODEL_PRICES)
  for model_id, value in data.items():
    if model_id not in ALLOWED_MODELS or not isinstance(value, dict):
      continue
    prices[model_id] = TokenPrices(
      input_per_1m=float(value["input_per_1m"]),
      output_per_1m=float(value["output_per_1m"]),
      cached_input_per_1m=float(value["cached_input_per_1m"]),
    )
  return prices


def preflight_models(model_ids: tuple[str, ...], *, timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS) -> dict[str, Any]:
  api_key = resolve_openai_api_key()
  if not api_key:
    return {
      "ok": False,
      "models": [
        {
          "model_id": model_id,
          "ok": False,
          "error": "OPENAI_API_KEY is not set",
        }
        for model_id in model_ids
      ],
    }
  client = OpenAI(api_key=api_key, timeout=timeout_seconds)
  checks = []
  for model_id in model_ids:
    try:
      model = client.models.retrieve(model_id)
      checks.append({
        "model_id": model_id,
        "ok": True,
        "raw": serialize_openai_response(model),
      })
    except Exception as exc:
      checks.append({
        "model_id": model_id,
        "ok": False,
        "error": f"{exc.__class__.__name__}: {exc}",
      })
  return {
    "ok": all(check["ok"] for check in checks),
    "models": checks,
  }


def resolve_openai_api_key() -> str | None:
  value = os.getenv("OPENAI_API_KEY", "").strip()
  return value or None


def serialize_openai_response(value: Any) -> Any:
  if value is None:
    return None
  if hasattr(value, "model_dump"):
    return value.model_dump(mode="json")
  if hasattr(value, "to_dict"):
    return value.to_dict()
  try:
    return json.loads(value.model_dump_json())
  except Exception:
    return str(value)


def int_or_zero(value: Any) -> int:
  try:
    return int(value)
  except (TypeError, ValueError):
    return 0


def render_markdown(results: list[EvalResult]) -> str:
  run_date = results[0].run_date if results else datetime.now().strftime("%Y-%m-%d")
  lines = [
    f"# 챗봇 모델별 80회 답변 평가 - {run_date}",
    "",
    "| 문항 ID | 분류 | 질문 | 실행군 | 모델 ID | 상태 | 기대 경로 | 실제 경로 | 기대 핸들러 | 실제 핸들러 | 도구 호출 여부 | fallback 사용 여부 | 답변 정상 여부 | 답변 충실도 | 답변 품질 메모 | 소요 시간(ms) | 입력 토큰 | 출력 토큰 | 캐시 토큰 | 전체 토큰 | 예상 비용(USD) | 답변 길이 | 답변 참조 | 비고 |",
    "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|",
  ]
  for result in results:
    lines.append(
      "| "
      + " | ".join([
        result.case_id,
        result.category,
        escape_table(result.question),
        result.run_group,
        result.model_id,
        result.status,
        result.expected_path,
        result.actual_path,
        ", ".join(result.expected_handlers) or "-",
        ", ".join(result.actual_handlers) or "-",
        bool_label(result.tool_called),
        bool_label(result.fallback_used),
        bool_label(result.answer_ok),
        result.answer_fidelity,
        escape_table(result.quality_note or "-"),
        str(result.elapsed_ms),
        str(result.input_tokens),
        str(result.output_tokens),
        str(result.cached_tokens),
        str(result.total_tokens),
        str(result.estimated_cost_usd),
        str(result.answer_length),
        f"[전문](#{result.answer_ref})",
        escape_table(result.notes or "-"),
      ])
      + " |"
    )

  lines.extend([
    "",
    "## 답변 전문",
    "",
  ])
  for result in results:
    lines.extend([
      f'### <a id="{result.answer_ref}"></a>{result.case_id} / {result.run_group}',
      "",
      f"- 질문: {result.question}",
      f"- 모델 ID: {result.model_id}",
      f"- 실제 핸들러: {', '.join(result.actual_handlers) or '-'}",
      f"- fallback 사용 여부: {str(result.fallback_used).lower()}",
      f"- 소요 시간(ms): {result.elapsed_ms}",
      f"- 전체 토큰: {result.total_tokens}",
      f"- 예상 비용(USD): {result.estimated_cost_usd}",
      "",
      "```text",
      result.answer or "-",
      "```",
      "",
    ])
  return "\n".join(lines)


def render_preflight_failure_markdown(run_date: str, preflight: dict[str, Any]) -> str:
  lines = [
    f"# 챗봇 모델별 80회 답변 평가 - {run_date}",
    "",
    "## Preflight Failed",
    "",
    "모델 접근 가능 여부 확인에 실패해 본 실행을 시작하지 않았습니다.",
    "",
    "| 모델 ID | 상태 | 오류 |",
    "|---|---|---|",
  ]
  for check in preflight.get("models", []):
    lines.append(
      "| "
      + " | ".join([
        str(check.get("model_id", "")),
        "성공" if check.get("ok") else "실패",
        escape_table(str(check.get("error", "-"))),
      ])
      + " |"
    )
  return "\n".join(lines)


def write_jsonl(path: Path, results: list[EvalResult]) -> None:
  with path.open("w", encoding="utf-8") as output:
    for result in results:
      output.write(json.dumps(asdict(result), ensure_ascii=False, default=str) + "\n")


def write_preflight_failure_jsonl(path: Path, run_date: str, preflight: dict[str, Any]) -> None:
  with path.open("w", encoding="utf-8") as output:
    for check in preflight.get("models", []):
      row = {
        "run_date": run_date,
        "event": "preflight_failed",
        "model_id": check.get("model_id"),
        "ok": check.get("ok"),
        "error": check.get("error"),
        "raw": check.get("raw"),
      }
      output.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def escape_table(value: str) -> str:
  return str(value).replace("|", "\\|").replace("\r\n", "\n").replace("\n", "<br>")


def bool_label(value: bool) -> str:
  return "Y" if value else "N"


if __name__ == "__main__":
  raise SystemExit(main())
