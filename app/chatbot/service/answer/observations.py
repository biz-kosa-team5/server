from __future__ import annotations

from typing import Any

from .context import ChatbotAnswerContext, is_successful_fragment
from .formatters.comparison import compact_comparison_results
from .formatters.legal_contract import compact_legal_contract_sources
from .formatters.recommendation import compact_recommendation_results


MAX_RECOMMENDATION_RESULTS = 5
MAX_PRICE_TREND_ROWS = 12
MAX_SIMPLE_LOOKUP_ROWS = 3
MAX_REGION_TRADE_HISTORY_ROWS = 5
MAX_LEGAL_SOURCES = 7
MAX_LEGAL_SOURCE_CONTENT_LENGTH = 12000


def build_answer_observations(context: ChatbotAnswerContext) -> dict[str, Any]:
  result_shape = "multiple" if isinstance(context.result, list) else "single"
  successful_observations = [
    compact_fragment(fragment)
    for fragment in context.fragments
    if is_successful_fragment(fragment)
  ]
  failed_observations = [
    compact_failed_fragment(fragment)
    for fragment in context.fragments
    if not is_successful_fragment(fragment)
  ]

  return {
    "question": context.question,
    "success": context.success,
    "status": context.status,
    "message": context.message,
    "executionSummary": context.executionSummary,
    "resultShape": result_shape,
    "successfulObservations": successful_observations,
    "failedObservations": failed_observations,
    "singleResult": compact_result(context.result) if result_shape == "single" else None,
    "multipleResults": compact_result(context.result) if result_shape == "multiple" else [],
    "uiSummary": compact_ui_summary(context.uiSummary),
    "uiArtifacts": compact_ui_artifacts(context.uiArtifacts),
    "rawResponse": compact_raw_response(context),
  }


def compact_fragment(fragment: dict[str, Any]) -> dict[str, Any]:
  return {
    "index": fragment.get("index"),
    "text": fragment.get("text"),
    "status": fragment.get("status"),
    "result": compact_result(fragment.get("result")),
  }


def compact_failed_fragment(fragment: dict[str, Any]) -> dict[str, Any]:
  result = fragment.get("result")
  compacted = {
    "index": fragment.get("index"),
    "text": fragment.get("text"),
    "status": fragment.get("status"),
  }
  if isinstance(result, dict):
    for key in ("handler", "agent", "reason", "message", "suggestedQuestions"):
      if key in result:
        compacted[key] = strip_nested_answers(result.get(key))
    nested = compact_result(result)
    if nested:
      compacted["result"] = nested
  return compacted


def compact_raw_response(context: ChatbotAnswerContext) -> dict[str, Any]:
  return {
    "question": context.question,
    "success": context.success,
    "status": context.status,
    "message": context.message,
    "uiSummary": compact_ui_summary(context.uiSummary),
    "fragments": [
      compact_fragment_metadata(fragment)
      for fragment in context.fragments
    ],
    "executionSummary": context.executionSummary,
  }


def compact_fragment_metadata(fragment: dict[str, Any]) -> dict[str, Any]:
  return {
    "index": fragment.get("index"),
    "text": fragment.get("text"),
    "status": fragment.get("status"),
  }


def compact_ui_summary(value: dict[str, Any] | None) -> dict[str, Any]:
  if not isinstance(value, dict):
    return {
      "hasMapFocus": False,
      "artifactTypes": [],
    }
  return {
    "hasMapFocus": value.get("hasMapFocus") is True,
    "primaryTargetName": clean_str(value.get("primaryTargetName")),
    "primaryActionLabel": clean_str(value.get("primaryActionLabel")),
    "artifactTypes": [
      clean_str(item)
      for item in value.get("artifactTypes", [])
      if clean_str(item)
    ] if isinstance(value.get("artifactTypes"), list) else [],
  }


def compact_ui_artifacts(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
  summaries = []
  for artifact in values:
    if not isinstance(artifact, dict):
      continue
    artifact_type = clean_str(artifact.get("type"))
    if not artifact_type:
      continue
    summary = {
      "type": artifact_type,
      "title": clean_str(artifact.get("title")),
    }
    if artifact_type == "comparison_bar_chart":
      summary["metricLabels"] = [
        clean_str(metric.get("label"))
        for metric in artifact.get("metrics", [])
        if isinstance(metric, dict) and clean_str(metric.get("label"))
      ]
      summary["itemCount"] = len(artifact.get("items", [])) if isinstance(artifact.get("items"), list) else 0
    elif artifact_type == "trend_line_chart":
      summary["pointCount"] = len(artifact.get("points", [])) if isinstance(artifact.get("points"), list) else 0
    elif artifact_type in {"ranking_list", "recommendation_list"}:
      summary["itemCount"] = len(artifact.get("items", [])) if isinstance(artifact.get("items"), list) else 0
    summaries.append(summary)
  return summaries


def compact_result(value: Any) -> Any:
  if isinstance(value, list):
    return [compact_result(item) for item in value]
  if not isinstance(value, dict):
    return value

  handler = clean_str(value.get("handler"))
  if handler == "simple_lookup":
    return compact_simple_lookup(value)
  if handler == "price_trend":
    return compact_price_trend(value)
  if handler == "recommendation":
    return compact_recommendation(value)
  if handler == "comparison":
    return compact_comparison(value)
  if handler == "legal_contract":
    return compact_legal_contract(value)

  compacted = {}
  for key, item in value.items():
    if key == "answer":
      continue
    if key == "result":
      compacted[key] = compact_result(item)
    elif key == "results":
      compacted[key] = compact_result(item)
    else:
      compacted[key] = strip_nested_answers(item)
  return compacted


def compact_simple_lookup(result: dict[str, Any]) -> dict[str, Any]:
  compacted = pick(result, [
    "handler",
    "success",
    "query_type",
    "observation_type",
    "criteria",
    "units",
    "message",
    "reason",
    "candidates",
    "suggestedQuestions",
  ])
  data = result.get("data")
  if isinstance(data, list):
    row_limit = simple_lookup_row_limit(result)
    compacted["data"] = strip_nested_answers(data[:row_limit])
  return compacted


def simple_lookup_row_limit(result: dict[str, Any]) -> int:
  if clean_str(result.get("query_type")) == "region_trade_history":
    return MAX_REGION_TRADE_HISTORY_ROWS
  return MAX_SIMPLE_LOOKUP_ROWS


def compact_price_trend(result: dict[str, Any]) -> dict[str, Any]:
  compacted = pick(result, [
    "handler",
    "success",
    "query_type",
    "observation_type",
    "criteria",
    "units",
    "summary",
    "summary_metrics",
    "row_count",
    "message",
    "reason",
    "candidates",
    "suggestedQuestions",
  ])
  rows = result.get("rows")
  if isinstance(rows, list):
    compacted["rows"] = strip_nested_answers(compact_price_trend_rows(result, rows))
  data = result.get("data")
  if isinstance(data, list):
    compacted["data"] = strip_nested_answers(compact_price_trend_rows(result, data))
  return compacted


def compact_price_trend_rows(result: dict[str, Any], rows: list[Any]) -> list[Any]:
  if len(rows) <= MAX_PRICE_TREND_ROWS:
    return rows

  observation_type = clean_str(result.get("observation_type") or result.get("query_type"))
  if observation_type not in {"timeseries", "price_timeseries"}:
    return rows[:MAX_PRICE_TREND_ROWS]

  head_count = MAX_PRICE_TREND_ROWS // 2
  tail_count = MAX_PRICE_TREND_ROWS - head_count
  return rows[:head_count] + rows[-tail_count:]


def compact_recommendation(result: dict[str, Any]) -> dict[str, Any]:
  compacted = pick(result, [
    "handler",
    "success",
    "criteria",
    "message",
    "reason",
    "suggestedQuestions",
  ])
  results = result.get("results")
  if isinstance(results, list):
    compacted["results"] = compact_recommendation_results([
      item for item in results[:MAX_RECOMMENDATION_RESULTS]
      if isinstance(item, dict)
    ])
  return compacted


def compact_comparison(result: dict[str, Any]) -> dict[str, Any]:
  compacted = pick(result, [
    "handler",
    "success",
    "criteria",
    "missingApartmentNames",
    "message",
    "reason",
    "suggestedQuestions",
  ])
  results = result.get("results")
  if isinstance(results, list):
    compacted["results"] = compact_comparison_results([
      item for item in results
      if isinstance(item, dict)
    ])
  return compacted


def compact_legal_contract(result: dict[str, Any]) -> dict[str, Any]:
  compacted = pick(result, [
    "handler",
    "success",
    "question",
    "expandedTerms",
    "summary",
    "message",
    "reason",
    "suggestedQuestions",
  ])
  sources = result.get("sources")
  if isinstance(sources, list):
    compacted["sources"] = compact_legal_contract_sources(
      [source for source in sources[:MAX_LEGAL_SOURCES] if isinstance(source, dict)],
      content_limit=MAX_LEGAL_SOURCE_CONTENT_LENGTH,
    )
  return compacted


def pick(source: dict[str, Any], keys: list[str]) -> dict[str, Any]:
  return {
    key: strip_nested_answers(source[key])
    for key in keys
    if key in source
  }


def strip_nested_answers(value: Any) -> Any:
  if isinstance(value, list):
    return [strip_nested_answers(item) for item in value]
  if isinstance(value, dict):
    return {
      key: strip_nested_answers(item)
      for key, item in value.items()
      if key != "answer"
    }
  return value


def clean_str(value: Any) -> str:
  return value.strip() if isinstance(value, str) else ""
