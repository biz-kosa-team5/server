import asyncio
import json

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


def test_chatbot_answer_composer_sends_detailed_answer_policy(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  completions = RecordingCompletions()

  asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(success_context()))

  system_prompt = completions.calls[0]["messages"][0]["content"]
  assert "한 줄 결론" in system_prompt
  assert "복합 질문이면 fragments의 index 순서를 유지" in system_prompt
  assert "내부 처리 용어를 사용자에게 노출하지 마세요" in system_prompt
  assert "도메인별 요약 방식" in system_prompt
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


def test_chatbot_answer_composer_adds_missing_redevelopment_note_for_recommendation(monkeypatch):
  monkeypatch.setenv("OPENAI_API_KEY", "test-key")
  completions = RecordingCompletions(content="대치동 추천 후보는 개포우성1입니다. 도곡역과 대청중학교가 가깝고 생활편의시설도 확인됩니다.")
  context = success_context(result={
    "success": True,
    "handler": "recommendation",
    "message": "조건에 맞는 아파트를 조회했습니다.",
    "results": [{
      "complexName": "개포우성1",
      "infrastructure": {
        "nearestStation": {"name": "도곡역", "distanceM": 382},
        "nearestEducation": {"name": "대청중학교", "distanceM": 145},
        "nearbyLifestyle": [{"name": "연치과병원", "distanceM": 300}],
      },
      "redevelopmentInfo": [],
    }],
  })

  answer = asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(context))

  assert answer.startswith("조건에 맞는 추천 후보입니다.\n1) 개포우성1")
  assert "도곡역 382m" in answer
  assert "생활편의 연치과병원 300m" in answer
  assert "재건축/정비사업 정보 없음" in answer
  assert "\n" in answer
  assert len(answer) <= 1000


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
