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
from app.chatbot.service.answer.formatters.result import format_result_messages
from app.chatbot.service.answer.formatters.simple_lookup import format_simple_lookup_result


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
    "잠실엘스 위치는 서울 송파구 잠실동입니다. 좌표는 위도 37.5, 경도 127.1입니다."
  )


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


def test_result_formatter_prefers_feature_answer_for_answered_domains():
  assert format_result_messages({
    "success": True,
    "handler": "recommendation",
    "answer": "feature 단계에서 만든 추천 답변입니다.",
    "results": [
      {
        "complexName": "래미안대치팰리스",
        "latestDealAmount": 435000,
      },
    ],
  }) == ["feature 단계에서 만든 추천 답변입니다."]
