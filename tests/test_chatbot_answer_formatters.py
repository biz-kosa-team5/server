"""
LLM composer와 분리해서 근거가 명확한 fallback formatter만 검증합니다.
simple_lookup과 price_trend는 각 feature DTO가 보장하는 응답 필드에 맞춰 문장을 조립합니다.
"""
from app.chatbot.features.price_trend.dto import (
  ANALYSIS_RANKING,
  ANALYSIS_TIMESERIES,
  TrendSuccessObservation,
)
from app.chatbot.features.simple_lookup.dto import (
  QUERY_LOCATION,
  QUERY_TRADE_HISTORY,
  SimpleLookupObservation,
)
from app.chatbot.service.answer.formatters.price_trend import format_price_trend_result
from app.chatbot.service.answer.formatters.recommendation import format_recommendation_result
from app.chatbot.service.answer.formatters.comparison import format_comparison_result
from app.chatbot.service.answer.formatters.legal_contract import format_legal_contract_result
from app.chatbot.service.answer.formatters.result import format_result_messages
from app.chatbot.service.answer.formatters.simple_lookup import format_simple_lookup_result
from app.chatbot.service.answer.composer import finalize_answer_text
from app.chatbot.service.answer.context import ChatbotAnswerContext


def test_simple_lookup_formatter_uses_location_dto_shape():
  result = SimpleLookupObservation(
    query_type=QUERY_LOCATION,
    criteria={
      "query_type": QUERY_LOCATION,
      "target_name": "잠실엘스",
    },
    data=[
      {
        "complex_id": 1,
        "complex_name": "잠실엘스",
        "address": "서울 송파구 잠실동",
        "latitude": 37.5,
        "longitude": 127.1,
      },
    ],
    message="단지 위치를 조회했습니다.",
  ).model_dump(mode="json")

  assert format_simple_lookup_result(result) == (
    "잠실엘스 위치는 서울 송파구 잠실동입니다. 지도에 표시했습니다."
  )


def test_simple_lookup_formatter_renders_primary_location_with_candidates():
  answer = format_simple_lookup_result({
    "handler": "simple_lookup",
    "success": True,
    "query_type": QUERY_LOCATION,
    "criteria": {"target_name": "우성아파트"},
    "data": [
      {
        "complex_id": 1,
        "complex_name": "우성아파트",
        "address": "잠실동 101-1",
        "latitude": 37.5,
        "longitude": 127.1,
      },
    ],
    "candidates": [
      {"complex_id": 1, "complex_name": "우성아파트", "address": "잠실동 101-1"},
      {"complex_id": 2, "complex_name": "우성아파트", "address": "서초동 1326-17"},
    ],
  })

  assert "우성아파트 위치는 잠실동 101-1입니다." in answer
  assert "지도에 표시했습니다." in answer
  assert "같은 이름으로 확인되는 후보는 다음과 같습니다." in answer
  assert "1. 잠실동 우성아파트" in answer
  assert "2. 서초동 우성아파트" in answer


def test_simple_lookup_formatter_uses_trade_dto_shape():
  result = SimpleLookupObservation(
    query_type=QUERY_TRADE_HISTORY,
    criteria={
      "query_type": QUERY_TRADE_HISTORY,
      "target_name": "잠실엘스",
    },
    data=[
      {
        "complex_id": 1,
        "complex_name": "잠실엘스",
        "trade_id": 1,
        "deal_date": "2026-01-20",
        "deal_amount": 435000,
        "excl_area": 84.97,
        "floor": 15,
      },
    ],
  ).model_dump(mode="json")

  assert format_simple_lookup_result(result) == (
    "잠실엘스 실거래 내역은 2026-01-20 43.5억원 전용 84.97㎡ 15층입니다."
  )


def test_simple_lookup_formatter_renders_ambiguous_candidates():
  answer = format_simple_lookup_result({
    "handler": "simple_lookup",
    "success": False,
    "query_type": QUERY_LOCATION,
    "criteria": {"target_name": "우성아파트"},
    "reason": "ambiguous_target",
    "message": "여러 단지가 검색되었습니다.",
    "candidates": [
      {"complex_id": 1, "complex_name": "청담우성아파트", "address": "서울특별시 강남구 청담동 11-25"},
      {"complex_id": 2, "complex_name": "대치우성아파트", "address": "서울특별시 강남구 대치동 63"},
      {"complex_id": 3, "complex_name": "잠실우성아파트", "address": "서울특별시 송파구 잠실동 101"},
    ],
  })

  assert "우성아파트로 확인되는 단지는 다음과 같습니다." in answer
  assert "1. 청담동 청담우성아파트" in answer
  assert "2. 대치동 대치우성아파트" in answer
  assert "어느 단지인지" not in answer


def test_price_trend_formatter_uses_timeseries_observation_rows():
  result = TrendSuccessObservation(
    observation_type=ANALYSIS_TIMESERIES,
    criteria={},
    row_count=2,
    rows=[
      {
        "period_start": "2025-01-01",
        "avg_deal_amount": 100000,
        "trade_count": 2,
      },
      {
        "period_start": "2025-12-01",
        "avg_deal_amount": 120000,
        "trade_count": 2,
      },
    ],
  ).model_dump(mode="json")

  assert format_price_trend_result(result) == (
    "시세추이를 조회했습니다. 2025-01-01 평균 10.0억원에서 "
    "2025-12-01 평균 12.0억원으로 확인됩니다."
  )


def test_price_trend_formatter_includes_timeseries_target_name():
  result = TrendSuccessObservation(
    observation_type=ANALYSIS_TIMESERIES,
    criteria={"target_name": "잠실엘스"},
    row_count=2,
    rows=[
      {
        "period_start": "2025-01-01",
        "avg_deal_amount": 100000,
      },
      {
        "period_start": "2025-12-01",
        "avg_deal_amount": 120000,
      },
    ],
  ).model_dump(mode="json")

  assert format_price_trend_result(result).startswith("잠실엘스 시세추이를 조회했습니다.")


def test_price_trend_formatter_uses_price_per_sqm_timeseries_unit():
  result = TrendSuccessObservation(
    observation_type=ANALYSIS_TIMESERIES,
    criteria={},
    row_count=2,
    rows=[
      {
        "period_start": "2025-01-01",
        "avg_price_per_sqm": 1000,
        "trade_count": 2,
      },
      {
        "period_start": "2025-12-01",
        "avg_price_per_sqm": 1200,
        "trade_count": 2,
      },
    ],
  ).model_dump(mode="json")

  assert format_price_trend_result(result) == (
    "시세추이를 조회했습니다. 2025-01-01 평균 1,000만원/㎡에서 "
    "2025-12-01 평균 1,200만원/㎡로 확인됩니다."
  )


def test_price_trend_formatter_uses_ranking_observation_rows():
  result = TrendSuccessObservation(
    observation_type=ANALYSIS_RANKING,
    criteria={},
    row_count=2,
    rows=[
      {
        "rank": 1,
        "complex_name": "잠실엘스",
        "change_rate": 20,
      },
      {
        "rank": 2,
        "complex_name": "리센츠",
        "change_rate": 10,
      },
    ],
  ).model_dump(mode="json")

  assert format_price_trend_result(result) == (
    "가격 변화율 순위는 잠실엘스 20.00%, 리센츠 10.00%입니다."
  )


def test_price_trend_formatter_includes_ranking_target_name():
  result = TrendSuccessObservation(
    observation_type=ANALYSIS_RANKING,
    criteria={"target_name": "강남구"},
    row_count=1,
    rows=[
      {
        "rank": 1,
        "complex_name": "잠실엘스",
        "change_rate": 20,
      },
    ],
  ).model_dump(mode="json")

  assert format_price_trend_result(result) == "강남구 가격 변화율 순위는 잠실엘스 20.00%입니다."


def test_result_formatter_routes_recommendation_without_feature_answer():
  messages = format_result_messages({
    "success": True,
    "handler": "recommendation",
    "answer": "feature 단계에서 만든 추천 답변입니다.",
    "results": [
      {
        "complexName": "래미안대치팰리스",
        "latestDealAmount": 435000,
      },
    ],
  })

  assert messages[0].startswith("조회된 데이터 기준")
  assert "래미안대치팰리스" in messages[0]
  assert "feature 단계" not in messages[0]


def test_recommendation_formatter_includes_lifestyle_and_redevelopment_context():
  answer = format_recommendation_result({
    "handler": "recommendation",
    "success": True,
    "criteria": {"district": "송파구"},
    "results": [{
      "complexName": "잠실엘스",
      "latestDealAmountText": "25.0억원",
      "unitCnt": 5678,
      "useDate": "2008-09-01",
      "infrastructure": {
        "nearbyLifestyle": [
          {"name": "롯데백화점 잠실점", "subtype": "백화점", "distanceM": 620},
          {"name": "서울아산병원", "subtype": "병원", "distanceM": 780},
        ],
      },
      "redevelopmentInfo": [{"title": "잠실 일대 정비사업 관련 기사", "url": "https://example.com"}],
    }],
  })

  assert "800m 생활편의" in answer
  assert "롯데백화점 잠실점" in answer
  assert "재개발/정비사업 검색결과" in answer
  assert "상권이나 학군 평판처럼 데이터에 없는" not in answer


def test_comparison_formatter_includes_lifestyle_and_redevelopment_context():
  answer = format_comparison_result({
    "handler": "comparison",
    "success": True,
    "criteria": {"apartment_names": ["잠실엘스", "리센츠"]},
    "results": [
      {
        "complexName": "잠실엘스",
        "latestDealAmountText": "25.0억원",
        "unitCnt": 5678,
        "builtYear": 2008,
        "nearbyLifestyle": [{"name": "롯데백화점 잠실점", "subtype": "백화점", "distanceM": 620}],
        "redevelopmentInfo": [{"title": "잠실 일대 정비사업 관련 기사", "url": "https://example.com"}],
      },
      {
        "complexName": "리센츠",
        "latestDealAmountText": "24.0억원",
        "unitCnt": 5563,
        "builtYear": 2008,
        "nearbyLifestyle": [{"name": "서울아산병원", "subtype": "병원", "distanceM": 780}],
        "redevelopmentInfo": [],
      },
    ],
    "missingApartmentNames": [],
  })

  assert "800m 생활편의" in answer
  assert "롯데백화점 잠실점" in answer
  assert "재개발/정비사업 검색결과" in answer
  assert "상권, 학군 평판, 미래 가격 전망은 제공된 데이터만으로는 확인할 수 없습니다." not in answer


def test_comparison_formatter_keeps_available_results_with_missing_names():
  answer = format_comparison_result({
    "handler": "comparison",
    "success": False,
    "criteria": {"apartment_names": ["잠실엘스", "리센츠", "없는단지"]},
    "results": [
      {
        "complexName": "잠실엘스",
        "latestDealAmountText": "25.0억원",
      },
      {
        "complexName": "리센츠",
        "latestDealAmountText": "24.0억원",
      },
    ],
    "missingApartmentNames": ["없는단지"],
    "message": "일부 아파트를 찾지 못했습니다.",
  })

  assert "일부 아파트를 찾지 못했습니다: 없는단지" in answer
  assert "잠실엘스" in answer
  assert "리센츠" in answer


def test_comparison_formatter_avoids_duplicate_missing_message_when_too_few_results():
  answer = format_comparison_result({
    "handler": "comparison",
    "success": False,
    "criteria": {"apartment_names": ["잠실엘스", "없는단지"]},
    "results": [{"complexName": "잠실엘스"}],
    "missingApartmentNames": ["없는단지"],
    "message": "일부 아파트를 찾지 못했습니다.",
  })

  assert answer.count("일부 아파트를 찾지 못했습니다") == 1
  assert "비교할 아파트 데이터가 부족합니다" in answer


def test_comparison_formatter_renders_candidate_groups_with_resolved_context():
  answer = format_comparison_result({
    "handler": "comparison",
    "success": False,
    "criteria": {"apartment_names": ["우성 아파트", "삼성 3차 아파트"]},
    "results": [],
    "missingApartmentNames": [],
    "resolvedApartmentNames": ["삼성3차"],
    "resolutionNotes": ["삼성 3차 아파트는 단지로 확인했습니다."],
    "candidateGroups": [
      {
        "input": "우성 아파트",
        "status": "ambiguous",
        "candidates": [
          {"complex_id": 1, "complex_name": "대치우성아파트", "address": "서울특별시 강남구 대치동 63"},
          {"complex_id": 2, "complex_name": "청담우성아파트", "address": "서울특별시 강남구 청담동 11-25"},
        ],
      },
    ],
  })

  assert "삼성3차는 단지로 확인했습니다." in answer
  assert "우성 아파트로 확인되는 단지는 다음과 같습니다." in answer
  assert "대치우성아파트" in answer
  assert "비교를 진행하려면" not in answer


def test_finalize_answer_replaces_missing_text_when_candidates_exist():
  context = ChatbotAnswerContext(
    question="우성 아파트 찾아줘",
    success=False,
    status="failed",
    message="처리할 수 있는 질문이 없습니다.",
    fragments=[],
    result={
      "handler": "simple_lookup",
      "success": False,
      "query_type": QUERY_LOCATION,
      "criteria": {"target_name": "우성아파트"},
      "reason": "ambiguous_target",
      "message": "여러 단지가 검색되었습니다.",
      "candidates": [
        {"complex_id": 1, "complex_name": "청담우성아파트", "address": "서울특별시 강남구 청담동 11-25"},
        {"complex_id": 2, "complex_name": "대치우성아파트", "address": "서울특별시 강남구 대치동 63"},
      ],
    },
    executionSummary={"total": 1, "succeeded": 0, "failed": 1},
  )

  answer = finalize_answer_text("우성아파트를 찾을 수 없습니다.", context)

  assert "찾을 수 없습니다" not in answer
  assert "청담우성아파트" in answer
  assert "대치우성아파트" in answer
  assert "어느 단지인지" not in answer


def test_legal_contract_formatter_uses_sources_without_internal_fields():
  answer = format_legal_contract_result({
    "handler": "legal_contract",
    "success": True,
    "question": "계약금을 돌려받을 수 있나요",
    "sources": [
      {
        "documentId": 1,
        "lawName": "민법",
        "articleNo": "565",
        "articleTitle": "해약금",
        "paragraphNo": "1",
        "content": "당사자 일방이 이행에 착수할 때까지 교부자는 이를 포기하고 수령자는 그 배액을 상환하여 매매계약을 해제할 수 있다.",
        "score": 0.9,
        "sourceUrl": "https://example.com",
      },
    ],
    "summary": "관련 근거 조문은 민법 제565조입니다.",
  })

  assert "민법 제565조(해약금) 1항" in answer
  assert "매매계약을 해제할 수 있다" in answer
  assert "documentId" not in answer
  assert "0.9" not in answer
  assert "https://example.com" not in answer
