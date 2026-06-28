from types import SimpleNamespace

from app.chatbot.service.answer import ChatbotAnswerContext


def success_context(
  *,
  result: dict | None = None,
  status: str = "success",
  message: str = "질문을 처리했습니다.",
) -> ChatbotAnswerContext:
  result = result or {
    "success": True,
    "handler": "simple_lookup",
    "message": "잠실엘스 조회 결과입니다.",
  }
  return ChatbotAnswerContext(
    question="잠실엘스 위치 알려줘",
    success=True,
    status=status,
    message=message,
    fragments=[
      {
        "index": 0,
        "text": "잠실엘스 위치 알려줘",
        "status": "handled",
        "result": result,
      },
    ],
    result=result,
    executionSummary={
      "total": 1,
      "succeeded": 1,
      "failed": 0,
    },
  )


def partial_success_context() -> ChatbotAnswerContext:
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
  return ChatbotAnswerContext(
    question="잠실엘스 위치 알려줘 그리고 오늘 날씨 알려줘",
    success=True,
    status="partial_success",
    message="일부 질문만 처리했습니다.",
    fragments=[
      {
        "index": 0,
        "text": "잠실엘스 위치 알려줘",
        "status": "handled",
        "result": successful_result,
      },
      {
        "index": 1,
        "text": "오늘 날씨 알려줘",
        "status": "not_handled",
        "result": failed_result,
      },
    ],
    result=[successful_result, failed_result],
    executionSummary={
      "total": 2,
      "succeeded": 1,
      "failed": 1,
    },
  )


class RecordingCompletions:
  def __init__(self, content="최종 답변입니다.", error: Exception | None = None):
    self.content = content
    self.error = error
    self.calls = []

  def create(self, **kwargs):
    self.calls.append(kwargs)
    if self.error:
      raise self.error
    return SimpleNamespace(
      choices=[
        SimpleNamespace(
          message=SimpleNamespace(content=self.content),
        ),
      ],
    )


class RecordingClient:
  def __init__(self, completions: RecordingCompletions):
    self.completions = completions
    self.chat = SimpleNamespace(completions=completions)
