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


def test_chatbot_answer_composer_falls_back_without_api_key(monkeypatch):
  monkeypatch.delenv("OPENAI_API_KEY", raising=False)
  completions = RecordingCompletions(content="호출되면 안 됩니다.")

  answer = asyncio.run(ChatbotAnswerComposer(client=RecordingClient(completions)).compose(success_context()))

  assert answer == "잠실엘스 조회 결과입니다."
  assert completions.calls == []


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
