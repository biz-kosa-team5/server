from __future__ import annotations

from app.chatbot.service.conversation_memory import (
  build_conversation_memory_patch,
  normalize_conversation_context,
  resolve_contextual_question,
)


def memory_context() -> dict:
  return normalize_conversation_context({
    "version": "v1",
    "activeRegion": {
      "name": "대치동",
      "code": "11680106",
      "type": "neighborhood",
    },
    "activeComplex": {
      "complexId": 1001,
      "complexName": "래미안대치팰리스",
      "address": "대치동 1027",
    },
    "items": [
      {
        "index": 1,
        "kind": "complex",
        "complexId": 3810,
        "complexName": "풍림아이원2차202동",
        "address": "대치동 910-6",
      },
      {
        "index": 2,
        "kind": "complex",
        "complexId": 1001,
        "complexName": "래미안대치팰리스",
        "address": "대치동 1027",
      },
    ],
  })


def test_resolves_ordinal_item_reference():
  resolved, resolution = resolve_contextual_question(
    "두 번째 거 최근 1년 흐름도 알려줘",
    memory_context(),
  )

  assert resolved == "래미안대치팰리스 최근 1년 흐름도 알려줘"
  assert resolution == {
    "applied": True,
    "source": "ordinal_item",
    "matchedText": "두 번째 거",
    "resolvedTarget": "래미안대치팰리스",
  }


def test_resolves_active_complex_reference():
  resolved, resolution = resolve_contextual_question(
    "그거랑 잠실엘스 비교해줘",
    memory_context(),
  )

  assert resolved == "래미안대치팰리스랑 잠실엘스 비교해줘"
  assert resolution["source"] == "active_complex"


def test_resolves_partial_item_name_when_unique():
  resolved, resolution = resolve_contextual_question(
    "그중 래미안만 자세히 봐줘",
    memory_context(),
  )

  assert resolved == "래미안대치팰리스만 자세히 봐줘"
  assert resolution["source"] == "partial_item_name"


def test_resolves_active_region_for_latest_trade_followup():
  resolved, resolution = resolve_contextual_question(
    "거기 최신 실거래 5개 더 보여줘",
    memory_context(),
  )

  assert resolved == "대치동 최신 실거래 5개 더 보여줘"
  assert resolution["source"] == "active_region"


def test_keeps_original_without_context_candidate():
  resolved, resolution = resolve_contextual_question("그거 최근 실거래 알려줘", None)

  assert resolved == "그거 최근 실거래 알려줘"
  assert resolution["applied"] is False


def test_keeps_original_when_partial_name_is_ambiguous():
  context = memory_context()
  context["items"].append({
    "index": 3,
    "kind": "complex",
    "complexId": 2001,
    "complexName": "래미안테스트",
  })

  resolved, resolution = resolve_contextual_question("그중 래미안만 자세히 봐줘", context)

  assert resolved == "그중 래미안만 자세히 봐줘"
  assert resolution == {
    "applied": False,
    "reason": "partial_name_ambiguous",
  }


def test_memory_patch_limits_items_to_five():
  response = {
    "result": {
      "handler": "simple_lookup",
      "success": True,
      "query_type": "region_trade_history",
      "criteria": {
        "target_name": "대치동",
        "target_type": "neighborhood",
      },
      "data": [
        {
          "complex_id": index,
          "complex_name": f"테스트{index}",
          "trade_id": 10000 + index,
          "deal_date": "2026-06-01",
          "deal_amount": 100000 + index,
        }
        for index in range(1, 7)
      ],
    },
    "fragments": [],
  }

  patch = build_conversation_memory_patch(response)

  assert patch["version"] == "v1"
  assert patch["activeRegion"] == {
    "name": "대치동",
    "type": "neighborhood",
  }
  assert patch["lastHandler"] == "simple_lookup"
  assert patch["lastQueryType"] == "region_trade_history"
  assert len(patch["items"]) == 5
  assert patch["items"][0]["index"] == 1
  assert patch["items"][4]["complexName"] == "테스트5"
