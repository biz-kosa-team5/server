import asyncio
import json

from app.chatbot.features.simple_lookup.dto import (
  QUERY_REGION_PRICE_RANKING,
  QUERY_REGION_TRADE_HISTORY,
)
from app.chatbot.service.answer import ChatbotAnswerComposer, ChatbotAnswerContext
from app.chatbot.service.answer import composer as composer_module

from chatbot_answer_helpers import (
  RecordingClient,
  RecordingCompletions,
  partial_success_context,
  success_context,
)


def test_chatbot_answer_composer_returns_fake_llm_answer(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  completions = RecordingCompletions(content="조회 결과를 종합한 답변입니다.")
  composer = ChatbotAnswerComposer(client=RecordingClient(completions))
  context = success_context(result={
    "success": True,
    "handler": "simple_lookup",
    "message": "단지 위치를 조회했습니다.",
  })

  answer = asyncio.run(composer.compose(context))

  assert answer == "조회 결과를 종합한 답변입니다."
  assert len(completions.calls) == 1
  assert completions.calls[0]["messages"][1]["content"].startswith(
    "아래 JSON 데이터만 근거로 사용자 질문에 답변해줘."
  )


def test_chatbot_answer_composer_does_not_reuse_single_result_answer(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  completions = RecordingCompletions(content="최종 answer 계층에서 만든 답변입니다.")
  context = success_context(result={
    "success": True,
    "handler": "recommendation",
    "answer": "feature 단계에서 만든 추천 답변입니다.",
    "message": "조건에 맞는 아파트를 조회했습니다.",
  })

  answer = asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(context))

  assert answer == "최종 answer 계층에서 만든 답변입니다."
  assert len(completions.calls) == 1
  assert "feature 단계에서 만든 추천 답변입니다." not in completions.calls[0]["messages"][1]["content"]


def test_chatbot_answer_composer_uses_stable_region_trade_history_without_llm(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  completions = RecordingCompletions(content="호출되면 안 됩니다.")
  result = {
    "success": True,
    "handler": "simple_lookup",
    "query_type": QUERY_REGION_TRADE_HISTORY,
    "criteria": {
      "query_type": QUERY_REGION_TRADE_HISTORY,
      "target_name": "강남구",
    },
    "data": [
      {
        "complex_id": 1,
        "complex_name": "풍림아이원2차202동",
        "address": "대치동 910-6",
        "deal_date": "2026-06-23",
        "deal_amount": 255000,
        "excl_area": 156.21,
        "price_per_m2": 1632.42,
        "floor": 7,
      },
    ],
  }
  context = ChatbotAnswerContext.from_response_dict({
    **success_context(result=result).to_dict(),
    "uiSummary": {"hasMapFocus": True},
  })

  answer = asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(context))

  assert completions.calls == []
  assert answer == (
    "강남구의 최근 실거래가 1건은 다음과 같습니다.\n\n"
    "1) 풍림아이원2차202동\n"
    "거래일: 2026-06-23\n"
    "거래금액: 25.5억원\n"
    "전용면적: 156.21㎡\n"
    "㎡당 가격: 1,632.42만원\n"
    "층수: 7층\n"
    "주소: 대치동 910-6\n\n"
    "제공된 데이터 기준입니다.\n\n"
    "지도에 표시했습니다."
  )


def test_chatbot_answer_composer_uses_stable_region_price_ranking_without_llm(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  completions = RecordingCompletions(content="1억 8천만 원이라고 잘못 말하면 안 됩니다.")
  result = {
    "success": True,
    "handler": "simple_lookup",
    "query_type": QUERY_REGION_PRICE_RANKING,
    "criteria": {
      "query_type": QUERY_REGION_PRICE_RANKING,
      "target_name": "서초구",
      "price_order": "highest",
    },
    "data": [
      {
        "rank": 1,
        "region_name": "서초구",
        "complex_id": 1,
        "complex_name": "아크로리버파크",
        "address": "반포동 2-12",
        "deal_date": "2024-08-05",
        "deal_amount": 1800000,
        "excl_area": 234.91,
        "price_per_m2": 7662.51,
        "floor": 35,
      },
    ],
  }
  context = ChatbotAnswerContext.from_response_dict({
    **success_context(result=result).to_dict(),
    "uiSummary": {"hasMapFocus": True},
  })

  answer = asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(context))

  assert completions.calls == []
  assert "거래금액: 180.0억원" in answer
  assert "1억 8천만 원" not in answer
  assert "1,800,000,000원" not in answer
  assert answer.endswith("지도에 표시했습니다.")


def test_chatbot_answer_composer_sends_detailed_answer_policy(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  completions = RecordingCompletions()

  asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(success_context()))

  system_prompt = completions.calls[0]["messages"][0]["content"]
  assert "한 줄 결론" in system_prompt
  assert "복합 질문이면 fragments의 index 순서를 유지" in system_prompt
  assert "내부 처리 용어를 사용자에게 노출하지 마세요" in system_prompt
  assert "도메인별 요약 방식" in system_prompt
  assert "아래 비교표로 가격/거리 차이를 볼 수 있다" in system_prompt
  assert "추천 후보가 여러 개면 후보 사이에 빈 줄을 하나 넣으세요" in system_prompt
  assert '"이유:" 같은 라벨 없이 자연문장으로 추천 근거를 쓰세요' in system_prompt
  assert "추천 결과가 5개 있으면 5개를 모두 쓰고" in system_prompt
  assert "Markdown 문법을 사용하지 마세요" in system_prompt


def test_chatbot_answer_composer_sends_structured_llm_context(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  completions = RecordingCompletions()

  asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(partial_success_context()))

  user_message = completions.calls[0]["messages"][1]["content"]
  payload = json.loads(user_message.split("답변 조립을 위한 정리본이야.\n", 1)[1])
  assert payload["resultShape"] == "multiple"
  assert payload["successfulObservations"][0]["text"] == "잠실엘스 위치 알려줘"
  assert payload["failedObservations"][0]["text"] == "오늘 날씨 알려줘"
  assert payload["rawResponse"]["status"] == "partial_success"


def test_chatbot_answer_composer_strips_trade_aliases_from_llm_context(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  completions = RecordingCompletions(content="공식단지명 위치는 서울시 테스트구 테스트동 1입니다.")
  context = success_context(result={
    "success": True,
    "handler": "simple_lookup",
    "query_type": "location",
    "criteria": {"target_name": "별칭거래명"},
    "data": [
      {
        "complex_id": 1,
        "complex_name": "공식단지명",
        "trade_name": "별칭거래명",
        "address": "서울시 테스트구 테스트동 1",
      }
    ],
    "candidates": [
      {
        "complex_id": 1,
        "complex_name": "공식단지명",
        "trade_name": "별칭거래명",
        "address": "서울시 테스트구 테스트동 1",
      }
    ],
  })

  asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(context))

  user_message = completions.calls[0]["messages"][1]["content"]
  payload = json.loads(user_message.split("답변 조립을 위한 정리본이야.\n", 1)[1])
  assert payload["singleResult"]["data"][0]["complex_name"] == "공식단지명"
  assert "trade_name" not in json.dumps(payload, ensure_ascii=False)
  assert "tradeName" not in json.dumps(payload, ensure_ascii=False)


def test_chatbot_answer_composer_sends_ui_summary_without_action_coordinates(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  completions = RecordingCompletions()
  context = ChatbotAnswerContext.from_response_dict({
    **success_context().to_dict(),
    "uiActions": [
      {
        "type": "focus_map",
        "target": {
          "latitude": 37.5124,
          "longitude": 127.0821,
        },
      }
    ],
    "uiArtifacts": [
      {
        "type": "comparison_bar_chart",
        "title": "단지 비교",
        "metrics": [{"label": "최근 거래가"}],
        "items": [{}, {}],
      }
    ],
    "uiSummary": {
      "hasMapFocus": True,
      "primaryTargetName": "잠실엘스",
      "artifactTypes": ["comparison_bar_chart"],
    },
  })

  asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(context))

  user_message = completions.calls[0]["messages"][1]["content"]
  payload = json.loads(user_message.split("답변 조립을 위한 정리본이야.\n", 1)[1])
  assert payload["uiSummary"]["hasMapFocus"] is True
  assert payload["uiArtifacts"][0]["type"] == "comparison_bar_chart"
  assert "uiActions" not in payload
  assert "latitude" not in user_message
  assert "longitude" not in user_message


def test_chatbot_answer_composer_does_not_call_llm_for_total_failure(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  completions = RecordingCompletions()
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

  answer = asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(context))

  assert answer == "지원 가능한 질문은 단지 조회 질문입니다."
  assert completions.calls == []


def test_chatbot_answer_composer_falls_back_when_llm_raises(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  completions = RecordingCompletions(error=RuntimeError("boom"))
  context = success_context(result={
    "success": True,
    "handler": "recommendation",
    "message": "추천 결과 메시지입니다.",
  })

  answer = asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(context))

  assert answer == "추천 결과 메시지입니다."


def test_chatbot_answer_composer_falls_back_when_llm_returns_empty(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  completions = RecordingCompletions(content="  ")
  context = success_context(result={
    "success": True,
    "handler": "price_trend",
    "message": "시세 추이 결과 메시지입니다.",
  })

  answer = asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(context))

  assert answer == "시세 추이 결과 메시지입니다."


def test_chatbot_answer_composer_removes_coordinate_text(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  completions = RecordingCompletions(
    content="잠실엘스 위치를 확인했습니다. 좌표는 위도 37.5124, 경도 127.0821입니다. 지도에 표시했습니다."
  )

  answer = asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(success_context()))

  assert "위도" not in answer
  assert "경도" not in answer
  assert "37.5124" not in answer
  assert answer == "잠실엘스 위치를 확인했습니다. 지도에 표시했습니다."


def test_chatbot_answer_composer_removes_markdown_formatting(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  completions = RecordingCompletions(
    content=(
      "대치동에서 많이 오른 아파트 TOP 5입니다.\n\n"
      "1. **대치효성**: `31.81%` 상승했습니다.\n"
      "- 제공된 데이터 기준입니다."
    )
  )

  answer = asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(success_context()))

  assert "**" not in answer
  assert "`" not in answer
  assert "- 제공" not in answer
  assert "1) 대치효성: 31.81% 상승했습니다." in answer


def test_chatbot_answer_composer_falls_back_when_forbidden_term_is_returned(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  completions = RecordingCompletions(content="handler 결과로 지도 이동 tool을 실행했습니다.")
  context = success_context(result={
    "success": True,
    "handler": "simple_lookup",
    "message": "잠실엘스 위치는 서울특별시 송파구 잠실동 19입니다.",
  })

  answer = asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(context))

  assert answer == "잠실엘스 위치는 서울특별시 송파구 잠실동 19입니다."
  assert "handler" not in answer
  assert "tool" not in answer


def test_chatbot_answer_composer_limits_answer_to_1000_chars(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  completions = RecordingCompletions(content="문장입니다. " * 160)

  answer = asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(success_context()))

  assert len(answer) <= 1000


def test_chatbot_answer_composer_uses_long_deterministic_sequence_without_llm(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  completions = RecordingCompletions(content="호출되면 안 됩니다.")
  long_address = "서울특별시 서초구 반포동 생활편의와 교통 접근성 설명이 긴 주소 메모 " * 6
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
              "complexName": "서초그랑자이",
              "address": long_address,
              "latestDealAmount": 350000,
              "unitCnt": 1446,
              "useDate": "2021-06-01",
              "infrastructure": {
                "nearestStation": {"name": "교대역", "distanceM": 520},
                "nearestEducation": {"name": "서초초등학교", "distanceM": 430},
                "nearbyLifestyle": [{"name": "대형마트A", "distanceM": 420}],
              },
            },
            {
              "complexName": "래미안서초에스티지",
              "address": long_address,
              "latestDealAmount": 320000,
              "unitCnt": 421,
              "useDate": "2016-12-01",
              "infrastructure": {
                "nearestStation": {"name": "강남역", "distanceM": 610},
                "nearestEducation": {"name": "서이초등학교", "distanceM": 500},
                "nearbyLifestyle": [{"name": "대형마트B", "distanceM": 610}],
              },
            },
            {
              "complexName": "반포자이",
              "address": long_address,
              "latestDealAmount": 410000,
              "unitCnt": 3410,
              "useDate": "2009-03-01",
              "infrastructure": {
                "nearestStation": {"name": "고속터미널역", "distanceM": 700},
                "nearestEducation": {"name": "원촌초등학교", "distanceM": 650},
                "nearbyLifestyle": [{"name": "대형마트C", "distanceM": 730}],
              },
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
          "criteria": {"apartment_names": ["서초그랑자이", "래미안서초에스티지", "반포자이"]},
          "results": [
            {
              "complexName": "서초그랑자이",
              "latestDealAmount": 350000,
              "pyeong": 34,
              "pricePerPyeong": 10294,
              "unitCnt": 1446,
              "builtYear": 2021,
              "nearbyLifestyle": [{"name": "대형마트A", "distanceM": 420}],
            },
            {
              "complexName": "래미안서초에스티지",
              "latestDealAmount": 320000,
              "pyeong": 34,
              "pricePerPyeong": 9411,
              "unitCnt": 421,
              "builtYear": 2016,
              "nearbyLifestyle": [{"name": "대형마트B", "distanceM": 610}],
            },
            {
              "complexName": "반포자이",
              "latestDealAmount": 410000,
              "pyeong": 34,
              "pricePerPyeong": 12058,
              "unitCnt": 3410,
              "builtYear": 2009,
              "nearbyLifestyle": [{"name": "대형마트C", "distanceM": 730}],
            },
          ],
        },
      },
    ],
  })

  answer = asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(context))

  assert completions.calls == []
  assert len(answer) > 1000
  assert len(answer) <= 5000
  assert "먼저 조건에 맞는 추천 후보 3개입니다." in answer
  assert "이어서 위 추천 후보 3개를 비교하면 다음과 같습니다." in answer
  assert "종합하면" in answer


def test_chatbot_answer_composer_uses_per_candidate_context_for_recommendations(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  completions = RecordingCompletions(content="Alpha를 추천합니다. Alpha는 Mall A가 가까워 생활편의성이 좋습니다.")
  context = success_context(result={
    "success": True,
    "handler": "recommendation",
    "criteria": {"station_name": "Central"},
    "message": "추천 후보를 조회했습니다.",
    "results": [
      {
        "complexName": "Alpha",
        "matchedPois": [{"category": "station", "name": "Central Station", "distanceM": 100}],
        "latestDealAmountText": "10.0억원",
        "useDate": "2000-01-01",
        "infrastructure": {
          "nearbyLifestyle": [{"name": "Mall A", "distanceM": 154}],
        },
        "redevelopmentInfo": [{"title": "Alpha redevelopment plan"}],
      },
      {
        "complexName": "Beta",
        "matchedPois": [{"category": "station", "name": "Central Station", "distanceM": 240}],
        "latestDealAmountText": "12.0억원",
        "useDate": "2010-01-01",
        "infrastructure": {
          "nearbyLifestyle": [{"name": "Clinic B", "distanceM": 220}],
        },
        "redevelopmentInfo": [],
      },
    ],
  })

  answer = asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(context))

  assert len(completions.calls) == 1
  assert "1. Alpha" in answer
  assert "Mall A 154m" in answer
  assert "Alpha redevelopment plan" in answer
  assert "2. Beta" in answer
  assert "Clinic B 220m" in answer
  assert "Beta 기준" not in answer
  assert "정보 없음" not in answer
  assert "\n이유:" not in answer
  assert "\n" in answer
  assert len(answer) <= 1000


def test_chatbot_answer_composer_keeps_llm_recommendation_lines(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  completions = RecordingCompletions(content=(
    "역세권과 가격 데이터를 기준으로 보면 두 후보를 우선 볼 수 있습니다.\n"
    "잠실엘스 - 잠실역 420m, 최근 거래가 28억원이라 조건에 맞습니다.\n"
    "리센츠 - 잠실새내역 310m, 생활편의시설이 가까워 추천할 수 있습니다."
  ))
  context = success_context(result={
    "success": True,
    "handler": "recommendation",
    "results": [
      {"complexName": "잠실엘스"},
      {"complexName": "리센츠"},
    ],
  })

  answer = asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(context))

  assert "조건에 맞는 추천 후보입니다." not in answer
  assert "1. 잠실엘스\n잠실역 420m" in answer
  assert "\n\n2. 리센츠\n잠실새내역 310m" in answer
  assert "\n이유:" not in answer


def test_chatbot_answer_composer_breaks_inline_numbered_recommendations(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  completions = RecordingCompletions(content=(
    "조건에 맞는 후보입니다. 1. 잠실엘스 - 잠실역 420m와 최근 거래가 28억원이 근거입니다. "
    "2. 리센츠 - 잠실새내역 310m와 생활편의시설이 근거입니다."
  ))
  context = success_context(result={
    "success": True,
    "handler": "recommendation",
    "results": [
      {"complexName": "잠실엘스"},
      {"complexName": "리센츠"},
    ],
  })

  answer = asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(context))

  assert "조건에 맞는 후보입니다.\n\n1. 잠실엘스\n잠실역 420m" in answer
  assert "\n\n2. 리센츠\n잠실새내역 310m" in answer
  assert "\n이유:" not in answer


def test_chatbot_answer_composer_preserves_requested_recommendation_block_shape(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  completions = RecordingCompletions(content=(
    "조건에 맞는 후보입니다.\n"
    "1. 잠실엘스\n"
    "이유: 잠실역 420m와 최근 거래가 28억원이 근거입니다.\n\n"
    "2. 리센츠\n"
    "이유: 잠실새내역 310m와 생활편의시설이 근거입니다."
  ))
  context = success_context(result={
    "success": True,
    "handler": "recommendation",
    "results": [
      {"complexName": "잠실엘스"},
      {"complexName": "리센츠"},
    ],
  })

  answer = asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(context))

  assert "1. 잠실엘스\n잠실역 420m" in answer
  assert "\n\n2. 리센츠\n잠실새내역 310m" in answer
  assert "\n이유:" not in answer


def test_chatbot_answer_composer_merges_duplicate_candidate_heading(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  completions = RecordingCompletions(content=(
    "잠실역 근처의 학교가 가까운 아파트입니다.\n"
    "1. 미성\n"
    "잠실역 390m, 서울잠실초등학교 491m입니다.\n\n"
    "2. 진주\n\n"
    "2. 진주\n"
    "는 잠실역 704m, 서울잠실초등학교 196m입니다.\n\n"
    "3. 호수\n\n"
    "3. 호수\n"
    "아파트는 잠실역 621m, 서울송파초등학교 386m입니다."
  ))
  context = success_context(result={
    "success": True,
    "handler": "recommendation",
    "results": [
      {"complexName": "미성"},
      {"complexName": "진주"},
      {"complexName": "호수"},
    ],
  })

  answer = asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(context))

  assert answer.count("2. 진주") == 1
  assert answer.count("3. 호수") == 1
  assert "\n\n2. 진주\n잠실역 704m" in answer
  assert "\n\n3. 호수\n잠실역 621m" in answer


def test_chatbot_answer_composer_keeps_five_recommendation_blocks(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  completions = RecordingCompletions(content=(
    "추천 기준에 맞는 후보 5개입니다.\n"
    "1. 후보1 - 역 100m와 생활편의시설이 가까워 추천합니다. "
    "2. 후보2 - 학교 120m와 최근 거래가가 확인됩니다. "
    "3. 후보3 - 주변 병원과 상권이 가까워 생활편의가 좋습니다. "
    "4. 후보4 - 노후 단지와 정비사업 공개 검색 결과가 있어 참고할 수 있습니다. "
    "5. 후보5 - 역세권과 최근 거래 데이터가 확인됩니다."
  ))
  context = success_context(result={
    "success": True,
    "handler": "recommendation",
    "results": [{"complexName": f"후보{index}"} for index in range(1, 6)],
  })

  answer = asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(context))

  for index in range(1, 6):
    assert f"\n{index}. 후보{index}\n" in f"\n{answer}\n"
  assert "\n\n5. 후보5\n" in answer
  assert "\n이유:" not in answer


def test_chatbot_answer_composer_structured_recommendation_uses_available_count(monkeypatch):
  monkeypatch.delenv("OPENAI_API_KEY", raising=False)
  context = success_context(result={
    "success": True,
    "handler": "recommendation",
    "criteria": {"station_name": "잠실역"},
    "results": [
      {
        "complexName": "미성",
        "matchedPois": [{"category": "station", "name": "잠실(송파구청)역", "distanceM": 390.66}],
        "latestDealAmountText": "17.9억원",
        "infrastructure": {"nearbyLifestyle": []},
      },
      {
        "complexName": "진주",
        "matchedPois": [{"category": "station", "name": "잠실(송파구청)역", "distanceM": 704.55}],
        "latestDealAmountText": "24.0억원",
        "infrastructure": {"nearbyLifestyle": []},
      },
    ],
  })

  answer = asyncio.run(ChatbotAnswerComposer().compose(context))

  assert "1. 미성" in answer
  assert "\n\n2. 진주" in answer
  assert "3." not in answer
  assert "5개" not in answer
  assert "잠실(송파구청)역 391m" in answer


def test_chatbot_answer_composer_uses_injected_llm_client_without_api_key(monkeypatch):
  monkeypatch.delenv("OPENAI_API_KEY", raising=False)
  completions = RecordingCompletions(content="주입된 LLM client가 만든 답변입니다.")

  answer = asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(success_context()))

  assert answer == "주입된 LLM client가 만든 답변입니다."
  assert len(completions.calls) == 1


def test_chatbot_answer_composer_falls_back_without_api_key_or_client(monkeypatch):
  monkeypatch.delenv("OPENAI_API_KEY", raising=False)

  answer = asyncio.run(ChatbotAnswerComposer().compose(success_context()))

  assert answer == "잠실엘스 조회 결과입니다."


def test_resolve_openai_api_key_loads_environment(monkeypatch):
  monkeypatch.delenv("OPENAI_API_KEY", raising=False)

  def fake_load_environment():
    monkeypatch.setenv("OPENAI_API_KEY", "loaded-key")

  monkeypatch.setattr(composer_module, "load_environment", fake_load_environment)

  assert composer_module.resolve_openai_api_key() == "loaded-key"


def test_chatbot_answer_composer_normalizes_openai_model_prefix(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  monkeypatch.setenv("OPENAI_CHAT_MODEL", "openai:gpt-4o-mini")
  completions = RecordingCompletions()

  asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(success_context()))

  assert completions.calls[0]["model"] == "gpt-4o-mini"


def test_chatbot_answer_composer_skips_llm_after_rate_limit(monkeypatch):
  class FakeRateLimitError(RuntimeError):
    status_code = 429

  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  monkeypatch.setenv("CHATBOT_ANSWER_LLM_FAILURE_COOLDOWN_SECONDS", "60")
  monkeypatch.setattr(composer_module, "_ANSWER_LLM_DISABLED_UNTIL", 0.0)
  failing_completions = RecordingCompletions(error=FakeRateLimitError("quota"))
  fallback_context = success_context(result={
    "success": True,
    "handler": "simple_lookup",
    "message": "잠실엘스 위치 조회 결과입니다.",
  })

  first_answer = asyncio.run(
    ChatbotAnswerComposer(client=RecordingClient(failing_completions)).compose(fallback_context)
  )
  skipped_completions = RecordingCompletions(content="호출되면 안 됩니다.")
  second_answer = asyncio.run(
    ChatbotAnswerComposer(client=RecordingClient(skipped_completions)).compose(fallback_context)
  )

  assert first_answer == "잠실엘스 위치 조회 결과입니다."
  assert second_answer == "잠실엘스 위치 조회 결과입니다."
  assert len(failing_completions.calls) == 1
  assert skipped_completions.calls == []
