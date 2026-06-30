from app.chatbot.service.answer import ChatbotAnswerContext, fallback_answer

from chatbot_answer_helpers import partial_success_context, success_context


def test_chatbot_answer_fallback_uses_message_for_total_failure():
  context = ChatbotAnswerContext(
    question="오늘 날씨 알려줘",
    success=False,
    status="failed",
    message="처리할 수 있는 질문이 없습니다.",
    fragments=[],
    result={
      "success": False,
      "reason": "no_matching_tool",
      "message": "지원 가능한 질문은 단지 조회 질문입니다.",
    },
    executionSummary={
      "total": 1,
      "succeeded": 0,
      "failed": 1,
    },
  )

  assert fallback_answer(context) == "지원 가능한 질문은 단지 조회 질문입니다."


def test_chatbot_answer_fallback_uses_generic_success_message():
  assert fallback_answer(success_context()) == "잠실엘스 조회 결과입니다."


def test_chatbot_answer_fallback_formats_simple_lookup_location():
  context = success_context(result={
    "success": True,
    "handler": "simple_lookup",
    "query_type": "location",
    "criteria": {
      "complex_name": "잠실엘스",
    },
    "data": [
      {
        "complex_name": "잠실엘스",
        "address": "서울 송파구 잠실동",
        "latitude": 37.5,
        "longitude": 127.1,
      },
    ],
    "message": "단지 위치를 조회했습니다.",
  })

  assert fallback_answer(context) == "잠실엘스 위치는 서울 송파구 잠실동입니다. 지도에 표시했습니다."


def test_chatbot_answer_fallback_formats_partial_success():
  assert fallback_answer(partial_success_context()) == (
    "잠실엘스 위치 조회 결과입니다.\n"
    "오늘 날씨 알려줘는 처리하지 못했습니다. 지원 가능한 질문이 아닙니다."
  )


def test_chatbot_answer_fallback_formats_nested_partial_success():
  successful_result = {
    "success": True,
    "handler": "simple_lookup",
    "message": "잠실엘스 위치 조회 결과입니다.",
  }
  failed_result = {
    "success": False,
    "reason": "no_matching_tool",
    "message": "지원 가능한 질문이 아닙니다.",
  }
  aggregate_result = {
    "success": True,
    "status": "partial_success",
    "message": "일부 전문 에이전트 결과만 처리했습니다.",
    "results": [successful_result, failed_result],
  }
  context = success_context(
    result=aggregate_result,
    status="partial_success",
    message="일부 질문만 처리했습니다.",
  )

  assert fallback_answer(context) == (
    "잠실엘스 위치 조회 결과입니다.\n"
    "지원 가능한 질문이 아닙니다."
  )


def test_chatbot_answer_fallback_formats_failed_specialist_wrapper_message():
  lookup_result = {
    "agent": "lookup_agent",
    "success": True,
    "result": {
      "success": True,
      "handler": "simple_lookup",
      "message": "잠실엘스 위치 조회 결과입니다.",
    },
  }
  failed_legal_result = {
    "agent": "legal_contract_agent",
    "success": False,
    "result": {
      "success": False,
      "reason": "insufficient_evidence",
      "message": "답변을 생성할 충분한 법령 근거를 찾지 못했습니다.",
    },
  }
  context = success_context(
    result={
      "success": True,
      "status": "partial_success",
      "message": "일부 전문 에이전트 결과만 처리했습니다.",
      "results": [lookup_result, failed_legal_result],
    },
    status="partial_success",
    message="일부 질문만 처리했습니다.",
  )

  assert fallback_answer(context) == (
    "잠실엘스 위치 조회 결과입니다.\n"
    "답변을 생성할 충분한 법령 근거를 찾지 못했습니다."
  )


def test_chatbot_answer_fallback_formats_price_trend_summary():
  context = success_context(result={
    "success": True,
    "handler": "price_trend",
    "query_type": "complex_trend",
    "summary": {
      "primary_metric": "avg_deal_amount",
      "first_period": "2025-01",
      "last_period": "2025-12",
      "first_value": 100000,
      "last_value": 120000,
      "change_rate": 20,
      "total_trade_count": 4,
    },
    "data": [],
    "message": "단지 시세추이를 조회했습니다.",
  })

  assert fallback_answer(context) == (
    "시세추이를 조회했습니다. 2025-01 100,000만원에서 2025-12 120,000만원으로 변했습니다. "
    "변화율은 20.00%입니다. 거래 건수는 4건입니다."
  )


def test_chatbot_answer_fallback_includes_dependent_recommendation_and_comparison():
  context = success_context(result={
    "success": True,
    "status": "success",
    "message": "여러 전문 에이전트 결과를 처리했습니다.",
    "results": [
      {
        "agent": "recommendation_agent",
        "success": True,
        "result": {
          "handler": "recommendation",
          "success": True,
          "results": [
            {
              "complexName": "잠실엘스",
              "latestDealAmountText": "30억원",
            },
          ],
        },
      },
      {
        "agent": "comparison_agent",
        "success": True,
        "dependsOn": "recommendation_agent",
        "result": {
          "handler": "comparison",
          "success": True,
          "results": [
            {
              "complexName": "잠실엘스",
              "latestDealAmountText": "30억원",
            },
            {
              "complexName": "래미안대치팰리스",
              "latestDealAmountText": "40억원",
            },
          ],
        },
      },
    ],
  })

  answer = fallback_answer(context)

  assert "잠실엘스" in answer
  assert "래미안대치팰리스" in answer
  assert "먼저 조건에 맞는 추천 후보" in answer
  assert "이어서 위 추천 후보" in answer
  assert "종합하면" in answer


def test_chatbot_answer_fallback_includes_ambiguous_lookup_and_trend():
  context = success_context(result={
    "success": True,
    "status": "success",
    "message": "여러 전문 에이전트 결과를 처리했습니다.",
    "results": [
      {
        "agent": "lookup_agent",
        "success": True,
        "result": {
          "handler": "simple_lookup",
          "success": True,
          "query_type": "trade_history",
          "criteria": {"target_name": "잠실엘스"},
          "data": [
            {
              "complex_name": "잠실엘스",
              "deal_date": "2026-01-01",
              "deal_amount": 300000,
              "excl_area": 84,
            },
          ],
        },
      },
      {
        "agent": "price_trend_agent",
        "success": True,
        "result": {
          "handler": "price_trend",
          "success": True,
          "observation_type": "timeseries",
          "summary": {
            "primary_metric": "avg_deal_amount",
            "first_period": "2025-01",
            "last_period": "2025-12",
            "first_value": 280000,
            "last_value": 300000,
          },
        },
      },
    ],
  })

  answer = fallback_answer(context)

  assert "잠실엘스 실거래 내역" in answer
  assert "시세추이를 조회했습니다" in answer
