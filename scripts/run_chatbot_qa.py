from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any


SERVER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVER_ROOT.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "qa"
DEFAULT_QUESTIONNAIRE_PATH = REPO_ROOT / "docs" / "data" / "chatbot-questionnaire.md"


@dataclass(frozen=True)
class QaCase:
  id: str
  test_package: str
  question: str
  expected_plan_type: str
  expected_execution_path: str
  expected_handlers: tuple[str, ...]
  expected_plan_types: tuple[str, ...] = ()
  expected_execution_paths: tuple[str, ...] = ()
  expected_handler_options: tuple[tuple[str, ...], ...] = ()
  expected_status: tuple[str, ...] = ("success",)
  expected_answer_terms: tuple[str, ...] = ()
  answer_must_not_include: tuple[str, ...] = ()
  legal_required: bool = False
  legal_must_include: tuple[str, ...] = ()
  group: str = ""
  variant: str = ""
  tier: str = "regression"
  notes: str = ""


@dataclass
class QaResult:
  run_date: str
  id: str
  test_package: str
  tier: str
  question: str
  expected_plan_type: str
  expected_execution_path: str
  expected_handlers: list[str]
  expected_status: list[str]
  actual_plan_types: list[str]
  actual_execution_path: str
  actual_agents: list[str]
  actual_handlers: list[str]
  actual_status: str
  elapsed_ms: int
  token_check: str
  answer_ok: bool
  answer: str
  answer_excerpt: str
  nested_answer_absent: bool
  passed: bool
  notes: str = ""
  expected_handler_options: list[list[str]] = field(default_factory=list)
  payload: dict[str, Any] = field(default_factory=dict)
  legal_fail_fast_triggered: bool = False


QA_CASES: tuple[QaCase, ...] = (
  QaCase(
    id="SL-002",
    test_package="chatbot.qa.specialist_tool.lookup",
    question="래미안대치팰리스 위치 알려줘",
    expected_plan_type="single_feature",
    expected_execution_path="direct_feature",
    expected_handlers=("simple_lookup",),
    expected_answer_terms=("래미안대치팰리스",),
  ),
  QaCase(
    id="SL-018",
    test_package="chatbot.qa.specialist_tool.lookup",
    question="래미안대치팰리스 최근 실거래가 알려줘",
    expected_plan_type="single_feature",
    expected_execution_path="direct_feature",
    expected_handlers=("simple_lookup",),
    expected_answer_terms=("래미안대치팰리스",),
  ),
  QaCase(
    id="RC-021",
    test_package="chatbot.qa.direct_feature.recommendation",
    question="송파구 30억 이하 아파트 추천해줘",
    expected_plan_type="single_feature",
    expected_execution_path="direct_feature",
    expected_handlers=("recommendation",),
    expected_status=("success", "failed"),
    notes="데이터에 조건 충족 후보가 없으면 failed가 정상일 수 있다.",
  ),
  QaCase(
    id="CP-008",
    test_package="chatbot.qa.direct_feature.comparison",
    question="래미안대치팰리스랑 잠실엘스 비교해줘",
    expected_plan_type="single_feature",
    expected_execution_path="direct_feature",
    expected_handlers=("comparison",),
    expected_answer_terms=("래미안대치팰리스", "잠실엘스"),
  ),
  QaCase(
    id="PT-001",
    test_package="chatbot.qa.specialist_tool.price_trend",
    question="잠실엘스 시세 추이 알려줘",
    expected_plan_type="single_feature",
    expected_execution_path="direct_feature",
    expected_handlers=("price_trend",),
    expected_answer_terms=("잠실엘스",),
  ),
  QaCase(
    id="PT-010",
    test_package="chatbot.qa.specialist_tool.price_trend",
    question="최근 1년 강남구에서 많이 오른 아파트 TOP 5 알려줘",
    expected_plan_type="single_feature",
    expected_execution_path="direct_feature",
    expected_handlers=("price_trend",),
    expected_status=("success", "failed"),
    expected_answer_terms=("강남구",),
    notes="랭킹 데이터가 없으면 failed가 정상일 수 있다.",
  ),
  QaCase(
    id="LC-022",
    test_package="chatbot.qa.specialist_tool.legal_contract",
    question="매매 계약금 해제 규정 알려줘",
    expected_plan_type="single_feature",
    expected_execution_path="direct_feature",
    expected_handlers=("legal_contract",),
    expected_status=("success", "failed"),
    notes="deterministic 모드에서는 OpenAI embedding 미설정으로 failed가 정상일 수 있다.",
  ),
  QaCase(
    id="MX-FR-002",
    test_package="chatbot.qa.aggregate.fragmented",
    question="잠실엘스 위치 알려줘 그리고 오늘 날씨 알려줘",
    expected_plan_type="fragmented",
    expected_execution_path="fragmented",
    expected_handlers=("simple_lookup",),
    expected_status=("partial_success",),
    expected_answer_terms=("잠실엘스",),
  ),
  QaCase(
    id="MX-IN-001",
    test_package="chatbot.qa.aggregate.independent",
    question="강남구 아파트 추천하고 최근 시세 추이도 알려줘",
    expected_plan_type="independent_multi_feature",
    expected_execution_path="direct_independent_features",
    expected_handlers=("recommendation", "price_trend"),
    expected_status=("success", "partial_success"),
    expected_answer_terms=("강남구",),
  ),
  QaCase(
    id="MX-IN-004",
    test_package="chatbot.qa.aggregate.independent",
    question="래미안대치팰리스랑 잠실엘스 비교하고 계약 시 주의할 법도 알려줘",
    expected_plan_type="independent_multi_feature",
    expected_execution_path="direct_independent_features",
    expected_handlers=("comparison", "legal_contract"),
    expected_status=("success", "partial_success"),
    expected_answer_terms=("래미안대치팰리스", "잠실엘스"),
    notes="deterministic 모드에서는 legal_contract가 embedding_unavailable로 partial_success일 수 있다.",
  ),
  QaCase(
    id="MX-DP-001",
    test_package="chatbot.qa.aggregate.dependent",
    question="강남구 아파트 추천하고 후보 비교도 해줘",
    expected_plan_type="dependent_multi_feature",
    expected_execution_path="direct_dependent_features",
    expected_handlers=("recommendation", "comparison"),
    expected_status=("success", "partial_success", "failed"),
    notes="추천 후보가 2개 미만이면 비교 dependency가 실패할 수 있다.",
  ),
  QaCase(
    id="MX-AM-001",
    test_package="chatbot.qa.aggregate.ambiguous",
    question="잠실엘스 시세 알려줘",
    expected_plan_type="ambiguous_multi_feature",
    expected_execution_path="direct_ambiguous_features",
    expected_handlers=("simple_lookup", "price_trend"),
    expected_status=("success", "partial_success"),
    expected_answer_terms=("잠실엘스",),
  ),
  QaCase(
    id="MX-ST-001",
    test_package="chatbot.qa.aggregate.same_tool",
    question="강남구 시세추이랑 송파구 시세추이 알려줘",
    expected_plan_type="same_tool_multi_feature",
    expected_execution_path="direct_same_tool_features",
    expected_handlers=("price_trend", "price_trend"),
    expected_status=("success", "partial_success", "failed"),
    expected_answer_terms=("강남구", "송파구"),
  ),
  QaCase(
    id="MX-DD-001",
    test_package="chatbot.qa.aggregate.dedupe",
    question="잠실엘스 위치랑 잠실엘스 위치 알려줘",
    expected_plan_type="single_feature",
    expected_execution_path="direct_feature",
    expected_handlers=("simple_lookup",),
    expected_answer_terms=("잠실엘스",),
  ),
  QaCase(
    id="UB-001",
    test_package="chatbot.qa.known_gap.boundary",
    question="오늘 날씨 알려줘",
    expected_plan_type="unsupported_feature",
    expected_execution_path="direct_no_matching_tool",
    expected_handlers=("no_matching_tool",),
    expected_status=("failed",),
    tier="regression",
  ),
)


BANNED_ANSWER_TERMS = (
  "handler",
  "agent",
  "tool",
  "fragment",
  "execution",
  "planType",
  "dedupe",
  "selectedAgent",
)


def main() -> int:
  args = parse_args()
  configure_environment(live_llm=args.live_llm or args.live_http)
  if not args.live_http:
    import_app_modules()
    from app.database import SessionLocal, ensure_initialized

  if not args.live_llm and not args.live_http:
    disable_live_openai()

  selected_cases = filter_cases(load_cases(args), args.case)
  run_date = datetime.now().strftime("%Y-%m-%d")
  output_dir = Path(args.output_dir)
  output_dir.mkdir(parents=True, exist_ok=True)
  suite_name = args.suite_name or ("chatbot-qa-docs-results" if args.from_docs else "chatbot-qa-results")
  markdown_path = output_dir / f"{suite_name}-{run_date}.md"
  jsonl_path = output_dir / f"{suite_name}-{run_date}.jsonl"

  if args.live_http:
    results = asyncio.run(run_cases(
      None,
      selected_cases,
      run_date,
      strict_supervisor_first=args.live_llm,
      live_http=True,
      base_url=args.base_url,
      fail_fast_legal=args.fail_fast_legal,
    ))
  else:
    ensure_initialized()
    with SessionLocal() as session:
      results = asyncio.run(run_cases(
        session,
        selected_cases,
        run_date,
        strict_supervisor_first=args.live_llm,
        fail_fast_legal=args.fail_fast_legal,
      ))

  markdown_path.write_text(
    render_markdown(results, live_llm=args.live_llm, live_http=args.live_http, fail_fast_legal=args.fail_fast_legal),
    encoding="utf-8",
  )
  write_jsonl(jsonl_path, results)

  passed = sum(1 for result in results if result.passed)
  failed = len(results) - passed
  print(f"wrote {markdown_path}")
  print(f"wrote {jsonl_path}")
  print(f"qa summary: total={len(results)} passed={passed} failed={failed}")
  legal_fail_fast_triggered = any(result.legal_fail_fast_triggered for result in results)
  if legal_fail_fast_triggered:
    return 1
  return 0 if failed == 0 or args.allow_failures else 1


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description="Run deterministic chatbot QA cases and write docs/qa results.")
  parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
  parser.add_argument("--case", action="append", default=[], help="Run only matching case id. Can be repeated.")
  parser.add_argument("--from-docs", action="store_true", help="Load all cases from docs/data/chatbot-questionnaire.md.")
  parser.add_argument("--questionnaire-path", default=str(DEFAULT_QUESTIONNAIRE_PATH))
  parser.add_argument("--suite-name", default="")
  parser.add_argument("--live-llm", action="store_true", help="Keep OPENAI_API_KEY and use live answer composer.")
  parser.add_argument("--live-http", action="store_true", help="Call POST /api/v1/chatbot/query instead of importing the service.")
  parser.add_argument("--base-url", default="http://127.0.0.1:8080", help="Base URL used with --live-http.")
  parser.add_argument("--fail-fast-legal", action="store_true", help="Stop immediately when a legal_required=Y row misses legal sources/answer contract.")
  parser.add_argument("--allow-failures", action="store_true", help="Exit 0 even when QA cases fail.")
  return parser.parse_args()


def configure_environment(*, live_llm: bool) -> None:
  if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))
  if os.getenv("CHATBOT_QA_USE_EXISTING_DATABASE") != "1":
    os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
    os.environ.setdefault("DATA_IMPORT_DIR", str(SERVER_ROOT / "db" / "import"))
  if not live_llm:
    disable_live_openai()


def disable_live_openai() -> None:
  os.environ["OPENAI_API_KEY"] = ""


def import_app_modules() -> None:
  # Register legal RAG tables on Base.metadata before database initialization.
  import app.chatbot.features.legal_contract.rag.model  # noqa: F401


def load_cases_from_questionnaire(path: Path) -> tuple[QaCase, ...]:
  cases: list[QaCase] = []
  headers: list[str] = []
  for line in path.read_text(encoding="utf-8").splitlines():
    if not line.startswith("|"):
      continue
    cells = parse_markdown_row(line)
    if not cells or is_separator_row(cells):
      continue
    if cells[0] == "id":
      headers = cells
      continue
    if not headers or not re.match(r"^[A-Z]{2}(?:-[A-Z]+)?-\d{3}$", cells[0]):
      continue
    row = dict(zip(headers, cells, strict=False))
    case = case_from_questionnaire_row(row)
    if case is not None:
      cases.append(case)
  return tuple(cases)


def parse_markdown_row(line: str) -> list[str]:
  return [
    cell.strip().strip("`")
    for cell in line.strip().strip("|").split("|")
  ]


def is_separator_row(cells: list[str]) -> bool:
  return all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def case_from_questionnaire_row(row: dict[str, str]) -> QaCase | None:
  case_id = row.get("id", "").strip()
  question = row.get("question", "").strip()
  if not case_id or not question:
    return None

  if "legal_required" in row or "answer_must_include" in row:
    return complex_case_from_row(row)
  if "expected_handlers" in row:
    return mixed_case_from_row(row)
  return handler_case_from_row(row)


def complex_case_from_row(row: dict[str, str]) -> QaCase:
  case_id = row["id"].strip()
  expected_plan_text = row.get("expected_plan_type", "").strip()
  expected_path_text = row.get("expected_execution_path", "").strip()
  expected_handlers_text = row.get("expected_handlers", "").strip()
  handler_options = handler_options_from_text(expected_handlers_text)
  plan_options = plan_options_from_text(expected_plan_text) or tuple(split_required_terms(expected_plan_text))
  path_options = path_options_from_text(expected_path_text) or tuple(split_required_terms(expected_path_text))
  statuses = tuple(split_required_terms(row.get("expected_status", ""))) or ("success",)
  first_handlers = handler_options[0] if handler_options else ()
  group = row.get("group", "").strip()

  return QaCase(
    id=case_id,
    test_package=f"chatbot.qa.complex.{group or 'mixed'}",
    question=row["question"],
    expected_plan_type=plan_options[0] if plan_options else expected_plan_text,
    expected_execution_path=path_options[0] if path_options else expected_path_text,
    expected_handlers=first_handlers,
    expected_plan_types=plan_options,
    expected_execution_paths=path_options,
    expected_handler_options=handler_options,
    expected_status=statuses,
    expected_answer_terms=tuple(split_required_terms(row.get("answer_must_include", ""))),
    answer_must_not_include=tuple(split_required_terms(row.get("answer_must_not_include", ""))),
    legal_required=row.get("legal_required", "").strip().upper() == "Y",
    legal_must_include=tuple(split_required_terms(row.get("legal_must_include", ""))),
    group=group,
    variant=row.get("variant", "").strip(),
    tier="regression",
    notes=row.get("notes", "").strip(),
  )


def handler_case_from_row(row: dict[str, str]) -> QaCase:
  case_id = row["id"]
  expected_text = row.get("expected_handler", "").strip()
  handler_options = handler_options_from_text(expected_text)
  plan_options, path_options = plan_path_options_for_handlers(handler_options, case_id, expected_text)
  statuses = status_options_for_case(case_id, expected_text, handler_options)
  first_handlers = handler_options[0] if handler_options else ()

  return QaCase(
    id=case_id,
    test_package=test_package_for_case(case_id),
    question=row["question"],
    expected_plan_type=plan_options[0] if plan_options else "supervisor_llm",
    expected_execution_path=path_options[0] if path_options else "supervisor_execution_failed",
    expected_handlers=first_handlers,
    expected_plan_types=plan_options,
    expected_execution_paths=path_options,
    expected_handler_options=handler_options,
    expected_status=statuses,
    tier=tier_for_case(case_id, expected_text),
    notes=docs_case_note(expected_text),
  )


def mixed_case_from_row(row: dict[str, str]) -> QaCase:
  case_id = row["id"]
  expected_plan_text = row.get("expected_plan_type", "").strip()
  expected_path_text = row.get("expected_execution_path", "").strip()
  expected_handlers_text = row.get("expected_handlers", "").strip()
  handler_options = handler_options_from_text(expected_handlers_text)
  plan_options = plan_options_from_text(expected_plan_text)
  path_options = path_options_from_text(expected_path_text)
  if "known_gap" in expected_path_text and () not in handler_options:
    handler_options = (*handler_options, ())
  statuses = status_options_for_mixed_case(expected_path_text, row.get("answer_checks", ""))
  first_handlers = handler_options[0] if handler_options else ()

  return QaCase(
    id=case_id,
    test_package=test_package_for_case(case_id),
    question=row["question"],
    expected_plan_type=plan_options[0] if plan_options else "supervisor_llm",
    expected_execution_path=path_options[0] if path_options else "supervisor_execution_failed",
    expected_handlers=first_handlers,
    expected_plan_types=plan_options,
    expected_execution_paths=path_options,
    expected_handler_options=handler_options,
    expected_status=statuses,
    tier=tier_for_case(case_id, expected_plan_text + " " + expected_path_text),
    notes=docs_case_note(" / ".join(filter(None, [expected_plan_text, expected_path_text]))),
  )


def handler_options_from_text(value: str) -> tuple[tuple[str, ...], ...]:
  text = normalize_expected_text(value)
  if not text or text == "없음":
    return ((),)

  alternatives = re.split(r"\s*또는\s*|\s+or\s+|;", text)
  options = []
  for alternative in alternatives:
    handlers = [
      handler
      for handler in re.split(r"\s*(?:,|\+)\s*", alternative)
      if handler in {
        "simple_lookup",
        "recommendation",
        "comparison",
        "price_trend",
        "legal_contract",
        "no_matching_tool",
      }
    ]
    if not handlers:
      continue
    option = tuple(handlers)
    if option not in options:
      options.append(option)
  return tuple(options) or ((),)


def split_required_terms(value: str) -> list[str]:
  return [
    term.strip()
    for term in value.split(";")
    if term.strip()
  ]


def normalize_expected_text(value: str) -> str:
  text = value.strip()
  text = re.sub(r"\([^)]*\)", "", text)
  text = text.replace("부분 실패", "").replace("실패", "")
  text = text.replace("확장", "").replace("known_gap:", "")
  return " ".join(text.split())


def plan_path_options_for_handlers(
  handler_options: tuple[tuple[str, ...], ...],
  case_id: str,
  expected_text: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
  plan_options: list[str] = []
  path_options: list[str] = []
  for handlers in handler_options:
    if handlers == ("simple_lookup", "price_trend"):
      add_unique(plan_options, "ambiguous_multi_feature")
      add_unique(path_options, "direct_ambiguous_features")
      continue
    if len(handlers) > 1:
      add_unique(plan_options, "independent_multi_feature")
      add_unique(path_options, "direct_independent_features")
      continue
    handler = handlers[0] if handlers else ""
    if handler == "no_matching_tool":
      add_unique(plan_options, "unsupported_feature")
      add_unique(plan_options, "supervisor_llm")
      add_unique(path_options, "direct_no_matching_tool")
      add_unique(path_options, "supervisor_no_tool")
      add_unique(path_options, "supervisor_execution_failed")
      continue
    if handler in {"simple_lookup", "recommendation", "comparison", "price_trend", "legal_contract"}:
      add_unique(plan_options, "single_feature")
      add_unique(path_options, "direct_feature")

  if "known_gap" in expected_text or case_id.startswith("UB-"):
    add_unique(plan_options, "supervisor_llm")
    add_unique(path_options, "supervisor_initialization_failed")
    add_unique(path_options, "supervisor_execution_failed")
    add_unique(path_options, "supervisor_unavailable")

  return tuple(plan_options), tuple(path_options)


def plan_options_from_text(value: str) -> tuple[str, ...]:
  text = value.strip()
  options: list[str] = []
  if "fragment" in text:
    options.append("fragmented")
  for candidate in (
    "single_feature",
    "independent_multi_feature",
    "dependent_multi_feature",
    "ambiguous_multi_feature",
    "same_tool_multi_feature",
    "supervisor_llm",
    "unsupported_feature",
  ):
    if candidate in text:
      options.append(candidate)
  return tuple(dedupe(options))


def path_options_from_text(value: str) -> tuple[str, ...]:
  text = value.strip()
  options: list[str] = []
  if "fragmented" in text:
    options.append("fragmented")
  for candidate in (
    "direct_feature",
    "direct_independent_features",
    "direct_dependent_features",
    "direct_ambiguous_features",
    "direct_same_tool_features",
    "direct_supported_unsupported_features",
    "direct_no_matching_tool",
    "supervisor_aggregate",
    "supervisor_no_tool",
    "supervisor_execution_failed",
    "supervisor_unavailable",
  ):
    if candidate in text:
      options.append(candidate)
  if "known_gap" in text:
    options.extend([
      "direct_no_matching_tool",
      "supervisor_no_tool",
      "supervisor_initialization_failed",
      "supervisor_execution_failed",
      "supervisor_unavailable",
    ])
  return tuple(dedupe(options))


def status_options_for_case(
  case_id: str,
  expected_text: str,
  handler_options: tuple[tuple[str, ...], ...],
) -> tuple[str, ...]:
  text = expected_text
  if "실패" in text or "known_gap" in text or case_id.startswith("UB-"):
    return ("success", "partial_success", "failed")
  flattened = {handler for option in handler_options for handler in option}
  if flattened & {"recommendation", "comparison", "price_trend", "legal_contract", "no_matching_tool"}:
    return ("success", "partial_success", "failed")
  return ("success",)


def status_options_for_mixed_case(expected_path_text: str, answer_checks: str) -> tuple[str, ...]:
  text = f"{expected_path_text} {answer_checks}"
  if "partial_success" in text or "미지원" in text or "gap" in text:
    return ("success", "partial_success", "failed")
  return ("success", "partial_success")


def test_package_for_case(case_id: str) -> str:
  if case_id.startswith("SL-"):
    return "chatbot.qa.specialist_tool.lookup"
  if case_id.startswith("RC-"):
    return "chatbot.qa.known_gap.recommendation" if case_id == "RC-008" else "chatbot.qa.direct_feature.recommendation"
  if case_id.startswith("CP-"):
    return "chatbot.qa.known_gap.comparison" if case_id in {"CP-002", "CP-007"} else "chatbot.qa.direct_feature.comparison"
  if case_id.startswith("PT-"):
    return "chatbot.qa.specialist_tool.price_trend"
  if case_id.startswith("LC-"):
    return "chatbot.qa.specialist_tool.legal_contract"
  if case_id.startswith("UB-"):
    return "chatbot.qa.known_gap.boundary"
  if case_id.startswith("RV-"):
    return "chatbot.qa.robustness"
  if case_id.startswith("MX-FR-"):
    return "chatbot.qa.aggregate.fragmented"
  if case_id.startswith("MX-IN-"):
    return "chatbot.qa.aggregate.independent"
  if case_id.startswith("MX-DP-"):
    return "chatbot.qa.aggregate.dependent"
  if case_id.startswith("MX-AM-"):
    return "chatbot.qa.aggregate.ambiguous"
  if case_id.startswith("MX-ST-"):
    return "chatbot.qa.aggregate.same_tool"
  if case_id.startswith("MX-LLM-"):
    return "chatbot.qa.aggregate.supervisor"
  if case_id.startswith("MX-DD-"):
    return "chatbot.qa.aggregate.dedupe"
  return "chatbot.qa.docs"


def tier_for_case(case_id: str, expected_text: str) -> str:
  if case_id.startswith("RV-"):
    return "exploratory"
  if "known_gap" in expected_text or case_id.startswith("UB-") or case_id in {"RC-008", "CP-002", "CP-007"}:
    return "boundary"
  return "regression"


def docs_case_note(expected_text: str) -> str:
  if not expected_text:
    return ""
  if "known_gap" in expected_text or "실패" in expected_text or "또는" in expected_text:
    return f"docs expectation: {expected_text}"
  return ""


def add_unique(values: list[str], value: str) -> None:
  if value not in values:
    values.append(value)


def load_cases(args: argparse.Namespace) -> tuple[QaCase, ...]:
  if not args.from_docs:
    return QA_CASES
  return load_cases_from_questionnaire(Path(args.questionnaire_path))


def filter_cases(cases: tuple[QaCase, ...], case_ids: list[str]) -> tuple[QaCase, ...]:
  if not case_ids:
    return cases
  wanted = set(case_ids)
  return tuple(case for case in cases if case.id in wanted)


async def run_cases(
  session: Any,
  cases: tuple[QaCase, ...],
  run_date: str,
  *,
  strict_supervisor_first: bool,
  live_http: bool = False,
  base_url: str = "http://127.0.0.1:8080",
  fail_fast_legal: bool = False,
) -> list[QaResult]:
  results = []
  for case in cases:
    result = await run_case(
      session,
      case,
      run_date,
      strict_supervisor_first=strict_supervisor_first,
      live_http=live_http,
      base_url=base_url,
    )
    if fail_fast_legal and case.legal_required and is_legal_hard_gate_failure(result):
      result.legal_fail_fast_triggered = True
      results.append(result)
      break
    results.append(result)
  return results


async def run_case(
  session: Any,
  case: QaCase,
  run_date: str,
  *,
  strict_supervisor_first: bool = False,
  live_http: bool = False,
  base_url: str = "http://127.0.0.1:8080",
) -> QaResult:
  started_at = perf_counter()
  if live_http:
    payload = await post_chatbot_query(base_url, case.question)
  else:
    from app.chatbot.service.chatbot_service import handle_chatbot_query
    payload = await handle_chatbot_query(session, {"question": case.question})
  elapsed_ms = round((perf_counter() - started_at) * 1000)
  actual_plan_types = collect_plan_types(payload)
  actual_path = actual_execution_path(payload)
  actual_agents = collect_agents(payload)
  actual_handlers = collect_handlers(payload)
  payload["__qa_group"] = case.group or case.test_package.rsplit(".", 1)[-1]
  payload["__qa_variant"] = case.variant
  answer = payload.get("answer") if isinstance(payload.get("answer"), str) else ""
  nested_answer_absent = nested_answer_paths(payload) == [["answer"]]
  answer_ok = validate_answer(answer, case, nested_answer_absent)
  notes = result_notes(
    case,
    payload,
    actual_plan_types,
    actual_path,
    actual_handlers,
    answer_ok,
    nested_answer_absent,
    strict_supervisor_first=strict_supervisor_first,
  )
  passed = not notes

  return QaResult(
    run_date=run_date,
    id=case.id,
    test_package=case.test_package,
    tier=case.tier,
    question=case.question,
    expected_plan_type=case.expected_plan_type,
    expected_execution_path=case.expected_execution_path,
    expected_handlers=list(case.expected_handlers),
    expected_handler_options=[
      list(option)
      for option in expected_handler_options(case)
    ],
    expected_status=list(case.expected_status),
    actual_plan_types=actual_plan_types,
    actual_execution_path=actual_path,
    actual_agents=actual_agents,
    actual_handlers=actual_handlers,
    actual_status=str(payload.get("status", "")),
    elapsed_ms=elapsed_ms,
    token_check=collect_token_check(payload),
    answer_ok=answer_ok,
    answer=answer,
    answer_excerpt=excerpt(answer),
    nested_answer_absent=nested_answer_absent,
    passed=passed,
    notes="; ".join(notes) if notes else case.notes,
    payload=payload,
  )


async def post_chatbot_query(base_url: str, question: str) -> dict[str, Any]:
  return await asyncio.to_thread(post_chatbot_query_sync, base_url, question)


def post_chatbot_query_sync(base_url: str, question: str) -> dict[str, Any]:
  url = f"{base_url.rstrip('/')}/api/v1/chatbot/query"
  body = json.dumps({"question": question}).encode("utf-8")
  request = urllib.request.Request(
    url,
    data=body,
    method="POST",
    headers={
      "Content-Type": "application/json",
      "Accept": "application/json",
    },
  )
  try:
    with urllib.request.urlopen(request, timeout=180) as response:
      text = response.read().decode("utf-8")
      payload = json.loads(text)
      if isinstance(payload, dict):
        payload["__http_status"] = response.status
        return payload
      return {"__http_status": response.status, "__json_error": "response JSON is not an object", "answer": ""}
  except urllib.error.HTTPError as exc:
    text = exc.read().decode("utf-8", errors="replace")
    try:
      payload = json.loads(text)
    except json.JSONDecodeError:
      payload = {"answer": "", "__json_error": text}
    if isinstance(payload, dict):
      payload["__http_status"] = exc.code
      return payload
    return {"__http_status": exc.code, "__json_error": text, "answer": ""}
  except json.JSONDecodeError as exc:
    return {"__http_status": 200, "__json_error": str(exc), "answer": ""}
  except Exception as exc:
    return {
      "__http_status": 0,
      "__http_error": f"{exc.__class__.__name__}: {exc}",
      "status": "failed",
      "answer": "",
    }


def result_notes(
  case: QaCase,
  payload: dict[str, Any],
  actual_plan_types: list[str],
  actual_path: str,
  actual_handlers: list[str],
  answer_ok: bool,
  nested_answer_absent: bool,
  *,
  strict_supervisor_first: bool = False,
) -> list[str]:
  notes = []
  http_status = payload.get("__http_status")
  if http_status is not None and http_status != 200:
    notes.append(f"HTTP 200 expected, got {http_status}")
  if payload.get("__json_error"):
    notes.append(f"JSON parsing failed: {payload.get('__json_error')}")
  status = str(payload.get("status", ""))
  if status not in case.expected_status:
    notes.append(f"status expected {case.expected_status}, got {status}")
  plan_options = expected_plan_options(case)
  if not any(plan_type_matches(expected, actual_plan_types, payload) for expected in plan_options):
    notes.append(f"plan expected one of {plan_options}, got {actual_plan_types}")
  if not execution_path_ok(
    case,
    actual_path,
    actual_handlers,
    payload,
    strict_supervisor_first=strict_supervisor_first,
  ):
    path_options = expected_path_options(case)
    notes.append(f"path expected one of {path_options}, got {actual_path}")
  handler_options = expected_handler_options(case)
  if not any(handler_order_matches(expected, actual_handlers) for expected in handler_options):
    notes.append(f"handlers expected one of {handler_options}, got {actual_handlers}")
  if not answer_ok:
    notes.append("answer contract/content check failed")
  if not nested_answer_absent:
    notes.append("nested answer found")
  notes.extend(legal_result_notes(case, payload, actual_handlers))
  return notes


def expected_plan_options(case: QaCase) -> tuple[str, ...]:
  return case.expected_plan_types or (case.expected_plan_type,)


def expected_path_options(case: QaCase) -> tuple[str, ...]:
  return case.expected_execution_paths or (case.expected_execution_path,)


def expected_handler_options(case: QaCase) -> tuple[tuple[str, ...], ...]:
  return case.expected_handler_options or (case.expected_handlers,)


def plan_type_matches(expected: str, actual_plan_types: list[str], payload: dict[str, Any]) -> bool:
  if expected == "fragmented":
    return len(payload.get("fragments", [])) > 1
  return expected in actual_plan_types


def execution_path_matches(expected: str, actual_path: str, payload: dict[str, Any]) -> bool:
  if expected == "fragmented":
    return len(payload.get("fragments", [])) > 1
  return expected in actual_path.split(",")


def execution_path_ok(
  case: QaCase,
  actual_path: str,
  actual_handlers: list[str],
  payload: dict[str, Any],
  *,
  strict_supervisor_first: bool = False,
) -> bool:
  if strict_supervisor_first:
    return strict_supervisor_first_path_matches(case, actual_path, actual_handlers, payload)
  path_options = expected_path_options(case)
  if any(execution_path_matches(expected, actual_path, payload) for expected in path_options):
    return True
  return supervisor_first_path_matches(case, actual_path, actual_handlers)


def strict_supervisor_first_path_matches(
  case: QaCase,
  actual_path: str,
  actual_handlers: list[str],
  payload: dict[str, Any],
) -> bool:
  handler_options = expected_handler_options(case)
  if all(option == ("no_matching_tool",) for option in handler_options):
    return any(
      execution_path_matches(expected, actual_path, payload)
      for expected in expected_path_options(case)
    )
  paths = set(filter(None, actual_path.split(",")))
  if paths & direct_data_paths():
    return False
  if case.expected_plan_type == "fragmented" and len(payload.get("fragments", [])) > 1:
    return True
  return supervisor_first_path_matches(case, actual_path, actual_handlers)


def direct_data_paths() -> set[str]:
  return {
    "direct_feature",
    "direct_ambiguous_features",
    "direct_supported_unsupported_features",
    "direct_same_tool_features",
    "direct_independent_features",
    "direct_dependent_features",
    "hybrid_independent_features",
  }


def supervisor_first_path_matches(
  case: QaCase,
  actual_path: str,
  actual_handlers: list[str],
) -> bool:
  paths = set(filter(None, actual_path.split(",")))
  if not paths & {"specialist_tool", "supervisor_aggregate"}:
    return False
  handler_options = tuple(
    option
    for option in expected_handler_options(case)
    if option != ("no_matching_tool",)
  )
  if not handler_options:
    return False
  return any(
    handler_order_matches(expected_handlers, actual_handlers)
    for expected_handlers in handler_options
  )


def handler_prefix_matches(expected_handlers: tuple[str, ...], actual_handlers: list[str]) -> bool:
  return handler_order_matches(expected_handlers, actual_handlers)


def handler_order_matches(expected_handlers: tuple[str, ...], actual_handlers: list[str]) -> bool:
  if not expected_handlers:
    return True
  actual_index = 0
  for expected in expected_handlers:
    while actual_index < len(actual_handlers):
      if base_handler_name(actual_handlers[actual_index]) == base_handler_name(expected):
        actual_index += 1
        break
      actual_index += 1
    else:
      return False
  return True


def base_handler_name(handler: str) -> str:
  return handler.split(".", 1)[0]


def validate_answer(answer: str, case: QaCase, nested_answer_absent: bool) -> bool:
  if not answer.strip() or not nested_answer_absent:
    return False
  banned_terms = case.answer_must_not_include or BANNED_ANSWER_TERMS
  if any(term in answer for term in banned_terms):
    return False
  return all(term in answer for term in case.expected_answer_terms)


def legal_result_notes(case: QaCase, payload: dict[str, Any], actual_handlers: list[str]) -> list[str]:
  if not case.legal_required:
    return []
  notes: list[str] = []
  answer = payload.get("answer") if isinstance(payload.get("answer"), str) else ""
  if "legal_contract" not in [base_handler_name(handler) for handler in actual_handlers]:
    notes.append("legal_required expected legal_contract handler")
  legal_results = collect_legal_results(payload)
  if not any(result.get("success") is True for result in legal_results):
    notes.append("legal_required expected legal result success=true")
  if not any(isinstance(result.get("sources"), list) and result.get("sources") for result in legal_results):
    notes.append("legal_required expected at least one legal source")
  missing_terms = [term for term in case.legal_must_include if term not in answer]
  if missing_terms:
    notes.append(f"legal answer missing required terms: {', '.join(missing_terms)}")
  return notes


def collect_legal_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
  results: list[dict[str, Any]] = []

  def visit(value: Any) -> None:
    if isinstance(value, list):
      for item in value:
        visit(item)
      return
    if not isinstance(value, dict):
      return
    if value.get("handler") == "legal_contract":
      results.append(value)
    for key in ("result", "results", "fragments"):
      if key in value:
        visit(value.get(key))

  visit(payload)
  return results


def is_legal_hard_gate_failure(result: QaResult) -> bool:
  return any(
    marker in result.notes
    for marker in (
      "legal_required expected",
      "legal answer missing required terms",
      "HTTP 200 expected",
      "JSON parsing failed",
    )
  )


def actual_execution_path(payload: dict[str, Any]) -> str:
  paths = [
    str(execution.get("path"))
    for execution in fragment_executions(payload)
    if execution.get("path")
  ]
  return ",".join(paths)


def collect_plan_types(payload: dict[str, Any]) -> list[str]:
  return dedupe([
    str(execution.get("planType"))
    for execution in fragment_executions(payload)
    if execution.get("planType")
  ])


def collect_agents(payload: dict[str, Any]) -> list[str]:
  agents: list[str] = []
  for execution in fragment_executions(payload):
    selected_agents = execution.get("selectedAgents")
    if isinstance(selected_agents, list):
      agents.extend(str(agent) for agent in selected_agents)
    selected_agent = execution.get("selectedAgent")
    if isinstance(selected_agent, str):
      agents.append(selected_agent)
  return dedupe(agents)


def collect_handlers(payload: dict[str, Any]) -> list[str]:
  handlers: list[str] = []
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
  if handlers:
    return handlers
  return collect_result_handlers(payload.get("result"))


def collect_token_check(payload: dict[str, Any]) -> str:
  usage = first_usage_metadata(payload)
  if not usage:
    return "not_captured"

  prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
  completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
  total_tokens = usage.get("total_tokens")
  parts = []
  if prompt_tokens is not None:
    parts.append(f"prompt={prompt_tokens}")
  if completion_tokens is not None:
    parts.append(f"completion={completion_tokens}")
  if total_tokens is not None:
    parts.append(f"total={total_tokens}")
  return ", ".join(parts) if parts else "metadata_present"


def first_usage_metadata(value: Any) -> dict[str, Any] | None:
  if isinstance(value, list):
    for item in value:
      usage = first_usage_metadata(item)
      if usage:
        return usage
    return None
  if not isinstance(value, dict):
    return None

  for key in ("usage", "usage_metadata", "token_usage", "tokenUsage"):
    usage = value.get(key)
    if isinstance(usage, dict):
      return usage

  for item in value.values():
    usage = first_usage_metadata(item)
    if usage:
      return usage
  return None


def collect_result_handlers(value: Any) -> list[str]:
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
      handlers.append(handler)
    if "result" in item:
      visit(item.get("result"))
    if "results" in item:
      visit(item.get("results"))

  visit(value)
  return handlers


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


def nested_answer_paths(value: Any, path: list[Any] | None = None) -> list[list[Any]]:
  path = path or []
  paths: list[list[Any]] = []
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


def dedupe(values: list[str]) -> list[str]:
  result = []
  for value in values:
    if value not in result:
      result.append(value)
  return result


def excerpt(value: str, limit: int = 120) -> str:
  text = " ".join(value.split())
  if len(text) <= limit:
    return text
  return text[: limit - 1] + "…"


def render_markdown(
  results: list[QaResult],
  *,
  live_llm: bool,
  live_http: bool = False,
  fail_fast_legal: bool = False,
) -> str:
  total = len(results)
  passed = sum(1 for result in results if result.passed)
  failed = total - passed
  legal_fail_fast_triggered = any(result.legal_fail_fast_triggered for result in results)
  lines = [
    f"# Chatbot QA Results - {results[0].run_date if results else datetime.now().strftime('%Y-%m-%d')}",
    "",
    "## Summary",
    "",
    f"- mode: {run_mode_label(live_llm=live_llm, live_http=live_http)}",
    f"- total: {total}",
    f"- passed: {passed}",
    f"- failed: {failed}",
    f"- overall: {'PASS' if failed == 0 else 'FAIL'}",
    f"- legal fail-fast enabled: {'Y' if fail_fast_legal else 'N'}",
    f"- legal fail-fast triggered: {'Y' if legal_fail_fast_triggered else 'N'}",
    "",
    "## Group Success Rates",
    "",
    "| group | total | passed | failed | pass rate |",
    "|---|---:|---:|---:|---:|",
  ]
  for group, group_results in group_results_by_name(results).items():
    group_total = len(group_results)
    group_passed = sum(1 for result in group_results if result.passed)
    group_failed = group_total - group_passed
    rate = f"{(group_passed / group_total * 100):.1f}%" if group_total else "0.0%"
    lines.append(f"| {escape_table(group)} | {group_total} | {group_passed} | {group_failed} | {rate} |")

  handler_failures = [result for result in results if "handlers expected" in result.notes or "legal_required expected legal_contract handler" in result.notes]
  answer_failures = [result for result in results if "answer contract/content check failed" in result.notes or "legal answer missing required terms" in result.notes]
  lines.extend([
    "",
    "## Handler Missing Cases",
    "",
    "- " + ("; ".join(result.id for result in handler_failures) if handler_failures else "none"),
    "",
    "## Answer Contract Failures",
    "",
    "- " + ("; ".join(result.id for result in answer_failures) if answer_failures else "none"),
    "",
    "## Results",
    "",
    "| id | package | status | expected path | actual path | expected handlers | actual handlers | elapsed ms | token check | answer ok | nested answer absent | answer | notes |",
    "|---|---|---|---|---|---|---|---:|---|---|---|---|---|",
  ])
  for result in results:
    lines.append(
      "| "
      + " | ".join([
        result.id,
        result.test_package,
        "PASS" if result.passed else "FAIL",
        result.expected_execution_path,
        result.actual_execution_path or "-",
        expected_handlers_label(result),
        ", ".join(result.actual_handlers) or "-",
        str(result.elapsed_ms),
        escape_table(result.token_check),
        "Y" if result.answer_ok else "N",
        "Y" if result.nested_answer_absent else "N",
        escape_table(result.answer or "-"),
        escape_table(result.notes or "-"),
      ])
      + " |"
    )
  lines.extend([
    "",
    "## Full Answers",
    "",
  ])
  for result in results:
    lines.extend([
      f"### {result.id}",
      "",
      f"- question: {result.question}",
      "",
      result.answer or "-",
      "",
    ])
  return "\n".join(lines)


def run_mode_label(*, live_llm: bool, live_http: bool) -> str:
  if live_http:
    return "live_http"
  return "live_llm" if live_llm else "deterministic"


def group_results_by_name(results: list[QaResult]) -> dict[str, list[QaResult]]:
  grouped: dict[str, list[QaResult]] = {}
  for result in results:
    group = result.payload.get("__qa_group")
    if not isinstance(group, str) or not group:
      group = result.test_package.rsplit(".", 1)[-1]
    grouped.setdefault(group, []).append(result)
  return dict(sorted(grouped.items()))


def escape_table(value: str) -> str:
  return value.replace("|", "\\|").replace("\r\n", "\n").replace("\n", "<br>")


def expected_handlers_label(result: QaResult) -> str:
  if result.expected_handler_options:
    return format_handler_options(result.expected_handler_options)
  return ", ".join(result.expected_handlers) or "-"


def format_handler_options(options: list[list[str]]) -> str:
  formatted = [
    ", ".join(option) if option else "-"
    for option in options
  ]
  return " 또는 ".join(formatted) if formatted else "-"


def write_jsonl(path: Path, results: list[QaResult]) -> None:
  with path.open("w", encoding="utf-8") as output:
    for result in results:
      data = asdict(result)
      output.write(json.dumps(data, ensure_ascii=False, default=str) + "\n")


if __name__ == "__main__":
  raise SystemExit(main())
