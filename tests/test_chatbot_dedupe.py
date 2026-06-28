from app.chatbot.service.dedupe import (
  dedupe_specialist_results,
  dedupe_tool_results,
  result_signature,
)
from app.chatbot.service.supervisor import SpecialistAgentResult, aggregate_specialist_results


def test_dedupe_removes_identical_lookup_results():
  items = [
    {
      "handler": "simple_lookup",
      "success": True,
      "query_type": "location",
      "criteria": {"target_name": "잠실엘스"},
    },
    {
      "handler": "simple_lookup",
      "success": True,
      "query_type": "location",
      "criteria": {"target_name": "잠실엘스"},
    },
  ]

  deduped, count = dedupe_tool_results(items)

  assert deduped == [items[0]]
  assert count == 1


def test_dedupe_removes_identical_price_trend_results():
  items = [
    {
      "handler": "price_trend",
      "success": True,
      "criteria": {
        "analysis_type": "timeseries",
        "target_type": "region",
        "target_name": "강남구",
        "period": "1y",
      },
    },
    {
      "handler": "price_trend",
      "success": True,
      "criteria": {
        "analysis_type": "timeseries",
        "target_type": "region",
        "target_name": "강남구",
        "period": "1y",
      },
    },
  ]

  deduped, count = dedupe_tool_results(items)

  assert deduped == [items[0]]
  assert count == 1


def test_dedupe_keeps_price_trends_for_different_targets():
  items = [
    {
      "handler": "price_trend",
      "success": True,
      "criteria": {"analysis_type": "timeseries", "target_type": "region", "target_name": "강남구"},
    },
    {
      "handler": "price_trend",
      "success": True,
      "criteria": {"analysis_type": "timeseries", "target_type": "region", "target_name": "송파구"},
    },
  ]

  deduped, count = dedupe_tool_results(items)

  assert deduped == items
  assert count == 0


def test_dedupe_specialist_results_unwraps_domain_result_signature():
  first = SpecialistAgentResult(
    agent="lookup_agent",
    result={
      "handler": "simple_lookup",
      "success": True,
      "query_type": "location",
      "criteria": {"target_name": "잠실엘스"},
    },
  )
  second = SpecialistAgentResult(
    agent="lookup_agent",
    result={
      "handler": "simple_lookup",
      "success": True,
      "query_type": "location",
      "criteria": {"target_name": "잠실엘스"},
    },
  )

  deduped, count = dedupe_specialist_results([first, second])

  assert deduped == [first]
  assert count == 1
  assert result_signature(first) == result_signature(second)


def test_aggregate_specialist_results_recalculates_summary_after_dedupe():
  result = aggregate_specialist_results([
    SpecialistAgentResult(
      agent="lookup_agent",
      result={
        "handler": "simple_lookup",
        "success": True,
        "query_type": "location",
        "criteria": {"target_name": "잠실엘스"},
      },
    ),
    SpecialistAgentResult(
      agent="lookup_agent",
      result={
        "handler": "simple_lookup",
        "success": True,
        "query_type": "location",
        "criteria": {"target_name": "잠실엘스"},
      },
    ),
  ])

  assert result["executionSummary"] == {
    "total": 1,
    "succeeded": 1,
    "failed": 0,
  }
  assert len(result["results"]) == 1
