"""
LLM composer와 분리해서 근거가 명확한 fallback formatter만 검증합니다.
simple_lookup과 price_trend는 각 feature DTO가 보장하는 응답 필드에 맞춰 문장을 조립합니다.
"""
from app.chatbot.features.price_trend.dto import QUERY_COMPLEX_TREND, TrendResult
from app.chatbot.features.simple_lookup.dto import (
  QUERY_LOCATION,
  QUERY_TRADE,
  SimpleLookupCriteria,
  SimpleLookupResult,
)
from app.chatbot.service.answer.formatters.price_trend import format_price_trend_result
from app.chatbot.service.answer.formatters.result import format_result_messages
from app.chatbot.service.answer.formatters.simple_lookup import format_simple_lookup_result


def test_simple_lookup_formatter_uses_location_dto_shape():
  result = SimpleLookupResult.ok(
    query_type=QUERY_LOCATION,
    criteria=SimpleLookupCriteria(
      query_type=QUERY_LOCATION,
      complex_name="잠실엘스",
    ),
    data=[
      {
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
  result = SimpleLookupResult.ok(
    query_type=QUERY_TRADE,
    criteria=SimpleLookupCriteria(
      query_type=QUERY_TRADE,
      complex_name="잠실엘스",
    ),
    data=[
      {
        "complex_name": "잠실엘스",
        "deal_date": "2026-01-20",
        "deal_amount": 435000,
        "exclusive_area": 84.97,
        "floor": 15,
      },
    ],
    message="실거래 내역을 조회했습니다.",
  ).model_dump(mode="json")

  assert format_simple_lookup_result(result) == (
    "잠실엘스 실거래 내역은 2026-01-20 43.5억원 전용 84.97㎡ 15층입니다."
  )


def test_price_trend_formatter_uses_trend_result_summary_shape():
  result = TrendResult.ok(
    query_type=QUERY_COMPLEX_TREND,
    criteria={},
    data=[],
    summary={
      "primary_metric": "avg_deal_amount",
      "first_period": "2025-01",
      "last_period": "2025-12",
      "first_value": 100000,
      "last_value": 120000,
      "change_rate": 20,
      "total_trade_count": 4,
    },
    message="단지 시세추이를 조회했습니다.",
  ).model_dump(mode="json")

  assert format_price_trend_result(result) == (
    "시세추이를 조회했습니다. 2025-01 100,000만원에서 2025-12 120,000만원으로 변했습니다. "
    "변화율은 20.00%입니다. 거래 건수는 4건입니다."
  )


def test_price_trend_formatter_uses_price_per_sqm_summary_unit():
  result = TrendResult.ok(
    query_type=QUERY_COMPLEX_TREND,
    criteria={},
    data=[],
    summary={
      "primary_metric": "avg_price_per_sqm",
      "first_period": "2025-01",
      "last_period": "2025-12",
      "first_value": 1000,
      "last_value": 1200,
      "change_rate": 20,
      "total_trade_count": 4,
    },
    message="단지 시세추이를 조회했습니다.",
  ).model_dump(mode="json")

  assert format_price_trend_result(result) == (
    "시세추이를 조회했습니다. 2025-01 1,000만원/㎡에서 2025-12 1,200만원/㎡로 변했습니다. "
    "변화율은 20.00%입니다. 거래 건수는 4건입니다."
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
