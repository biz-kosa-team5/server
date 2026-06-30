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


def test_resolves_ordinal_item_reference_with_group_prefix_without_leaking_reference_word():
  resolved, resolution = resolve_contextual_question(
    "그중 첫 번째 최근 거래 보여줘",
    memory_context(),
  )

  assert resolved == "풍림아이원2차202동 최근 거래 보여줘"
  assert resolution == {
    "applied": True,
    "source": "ordinal_item",
    "matchedText": "그중 첫 번째",
    "resolvedTarget": "풍림아이원2차202동",
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
    "거기 지역 최신 실거래 5개 더 보여줘",
    memory_context(),
  )

  assert resolved == "대치동 최신 실거래 5개 더 보여줘"
  assert resolution["source"] == "active_region"


def test_generic_there_prefers_active_complex_over_stale_region():
  resolved, resolution = resolve_contextual_question(
    "거기 최근 거래 보여줘",
    memory_context(),
  )

  assert resolved == "래미안대치팰리스 최근 거래 보여줘"
  assert resolution == {
    "applied": True,
    "source": "active_complex",
    "matchedText": "거기",
    "resolvedTarget": "래미안대치팰리스",
  }


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


def test_memory_patch_stores_ambiguous_candidates():
  response = {
    "result": {
      "handler": "simple_lookup",
      "success": False,
      "query_type": "location",
      "criteria": {"target_name": "우성아파트"},
      "reason": "ambiguous_target",
      "message": "여러 단지가 검색되었습니다.",
      "candidates": [
        {
          "complex_id": index,
          "complex_name": f"우성후보{index}",
          "address": f"서울특별시 강남구 대치동 {index}",
          "score": 100 - index,
        }
        for index in range(1, 7)
      ],
    },
    "fragments": [],
  }

  patch = build_conversation_memory_patch(response)

  assert patch["lastHandler"] == "simple_lookup"
  assert patch["lastQueryType"] == "location"
  assert len(patch["items"]) == 5
  assert patch["items"][0] == {
    "index": 1,
    "kind": "complex",
    "complexId": 1,
    "complexName": "우성후보1",
    "address": "서울특별시 강남구 대치동 1",
  }
  assert "score" not in patch["items"][0]


def test_resolves_partial_item_reference_by_candidate_address():
  context = normalize_conversation_context({
    "version": "v1",
    "items": [
      {
        "index": 1,
        "kind": "complex",
        "complexId": 1,
        "complexName": "청담우성아파트",
        "address": "서울특별시 강남구 청담동 11-25",
      },
      {
        "index": 2,
        "kind": "complex",
        "complexId": 2,
        "complexName": "대치우성아파트",
        "address": "서울특별시 강남구 대치동 63",
      },
    ],
  })

  resolved, resolution = resolve_contextual_question("그중 대치동", context)

  assert resolved == "대치우성아파트"
  assert resolution["source"] == "partial_item_name"


def test_resolves_context_item_mention_by_region_and_partial_name():
  context = normalize_conversation_context({
    "version": "v1",
    "items": [
      {
        "index": 1,
        "kind": "complex",
        "complexId": 1,
        "complexName": "잠실우성아파트",
        "address": "서울특별시 송파구 잠실동 101",
      },
      {
        "index": 2,
        "kind": "complex",
        "complexId": 2,
        "complexName": "대치우성아파트",
        "address": "서울특별시 강남구 대치동 63",
      },
    ],
  })

  resolved, resolution = resolve_contextual_question("잠실동 우성으로 봐줘", context)

  assert resolved == "잠실우성아파트으로 봐줘"
  assert resolution["source"] == "context_item_mention"


def test_memory_patch_stores_location_lookup_as_active_complex():
  response = {
    "result": {
      "handler": "simple_lookup",
      "success": True,
      "query_type": "location",
      "criteria": {"target_name": "잠실엘스"},
      "data": [
        {
          "complex_id": 1002,
          "complex_name": "잠실엘스",
          "address": "서울특별시 송파구 잠실동 19",
        },
      ],
    },
    "fragments": [],
  }

  patch = build_conversation_memory_patch(response)

  assert patch["lastHandler"] == "simple_lookup"
  assert patch["lastQueryType"] == "location"
  assert patch["activeComplex"] == {
    "complexId": 1002,
    "complexName": "잠실엘스",
    "address": "서울특별시 송파구 잠실동 19",
  }
  assert patch["items"][0] == {
    "index": 1,
    "kind": "complex",
    "complexId": 1002,
    "complexName": "잠실엘스",
    "address": "서울특별시 송파구 잠실동 19",
  }


def test_does_not_rewrite_weak_followup_without_explicit_reference():
  resolved, resolution = resolve_contextual_question(
    "그럼 최근 거래는?",
    memory_context(),
  )

  assert resolved == "그럼 최근 거래는?"
  assert resolution == {
    "applied": False,
    "reason": "no_reference",
  }


def test_resolves_this_reference_when_active_complex_exists():
  resolved, resolution = resolve_contextual_question(
    "이건 시세 어때?",
    memory_context(),
  )

  assert resolved == "래미안대치팰리스 시세 어때?"
  assert resolution["source"] == "active_complex"
  assert resolution["matchedText"] == "이건"


def test_this_reference_with_only_candidates_stays_unresolved():
  context = normalize_conversation_context({
    "version": "v1",
    "items": [
      {
        "index": 1,
        "kind": "complex",
        "complexId": 1,
        "complexName": "청담우성아파트",
        "address": "서울특별시 강남구 청담동 11-25",
      },
      {
        "index": 2,
        "kind": "complex",
        "complexId": 2,
        "complexName": "대치우성아파트",
        "address": "서울특별시 강남구 대치동 63",
      },
    ],
  })

  resolved, resolution = resolve_contextual_question("그럼 이건 시세 어때?", context)

  assert resolved == "그럼 이건 시세 어때?"
  assert resolution == {
    "applied": False,
    "reason": "target_not_found",
  }
