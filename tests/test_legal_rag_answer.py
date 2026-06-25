import json
from types import SimpleNamespace

from app.chatbot.features.legal_contract.rag.dto.answer import (
  LegalAnswerDraft,
  LegalAnswerStatus,
)
from app.chatbot.features.legal_contract.rag.service.answer_generator import (
  OpenAILegalAnswerGenerator,
)
from app.chatbot.features.legal_contract.rag.service.answer_prompt import (
  MAX_ANSWER_SOURCES,
  build_legal_answer_messages,
)
from app.chatbot.features.legal_contract.rag.service.answer_service import LegalAnswerService


class FakeAnswerGenerator:
  def __init__(self, draft: LegalAnswerDraft | None = None, error: Exception | None = None):
    self.draft = draft
    self.error = error
    self.calls: list[list[dict[str, str]]] = []

  def generate(self, messages: list[dict[str, str]]) -> LegalAnswerDraft:
    self.calls.append(messages)
    if self.error is not None:
      raise self.error
    assert self.draft is not None
    return self.draft


class FakeCompletions:
  def __init__(self, content: str):
    self.content = content
    self.requests = []

  def create(self, **kwargs):
    self.requests.append(kwargs)
    return SimpleNamespace(
      choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))],
    )


def source(document_id: int, score: float = 0.7) -> dict:
  return {
    "documentId": document_id,
    "lawId": f"LAW-{document_id}",
    "lawName": "민법",
    "articleNo": f"제{document_id}조",
    "articleTitle": "해약금",
    "paragraphNo": "",
    "content": f"법령 근거 {document_id}",
    "score": score,
    "keywordScore": 0.1,
    "sourceUrl": f"https://example.com/{document_id}",
    "effectiveDate": "2026-06-22",
  }


def search_result(sources: list[dict]) -> dict:
  return {
    "handler": "legal_contract",
    "success": bool(sources),
    "question": "계약금을 돌려받을 수 있나요",
    "expandedTerms": ["해약금"],
    "sources": sources,
  }


def test_answer_prompt_uses_at_most_configured_sources():
  messages = build_legal_answer_messages(
    "계약금을 돌려받을 수 있나요?",
    [source(index) for index in range(1, 9)],
  )

  assert MAX_ANSWER_SOURCES == 7
  assert '"documentId": 1' in messages[1]["content"]
  assert '"documentId": 7' in messages[1]["content"]
  assert '"documentId": 8' not in messages[1]["content"]


def test_answer_service_combines_only_valid_db_citations():
  generator = FakeAnswerGenerator(LegalAnswerDraft(
    answer="계약 이행 전에는 해약금 규정에 따라 해제할 수 있습니다.",
    citedDocumentIds=[2, 999, 2],
    status=LegalAnswerStatus.ANSWERED,
  ))
  service = LegalAnswerService(generator)

  result = service.answer(
    "계약금을 돌려받을 수 있나요?",
    search_result([
      source(1, 0.8), source(2, 0.7), source(3, 0.6),
      source(4, 0.5), source(5, 0.4), source(6, 0.3),
      source(7, 0.2), source(8, 0.1),
    ]),
  )

  assert result["success"] is True
  assert result["answerStatus"] == "answered"
  assert result["retrievalScore"] == 0.8
  assert [item["documentId"] for item in result["citations"]] == [2]
  assert result["citations"][0]["lawName"] == "민법"
  assert "근거는 민법의 제2조(해약금)를 참조했습니다." in result["answer"]
  assert "출처" not in result["answer"]
  assert "시행일: 2026-06-22" not in result["answer"]
  assert "https://example.com/2" not in result["answer"]
  assert "[999]" not in result["answer"]
  assert len(result["sources"]) == 7
  json.dumps(result)


def test_answer_service_removes_model_written_reference_sentence():
  generator = FakeAnswerGenerator(LegalAnswerDraft(
    answer="계약 이행 전에는 해제할 수 있습니다.\n근거는 민법의 제2조를 참조했습니다.",
    citedDocumentIds=[2],
    status=LegalAnswerStatus.ANSWERED,
  ))
  service = LegalAnswerService(generator)

  result = service.answer(
    "계약금을 돌려받을 수 있나요?",
    search_result([source(2)]),
  )

  assert result["answer"].count("근거는") == 1
  assert result["answer"] == (
    "계약 이행 전에는 해제할 수 있습니다.\n\n"
    "근거는 민법의 제2조(해약금)를 참조했습니다."
  )


def test_answer_service_skips_llm_without_sources():
  generator = FakeAnswerGenerator()
  result = LegalAnswerService(generator).answer(
    "근거가 없는 질문",
    search_result([]),
  )

  assert result["success"] is False
  assert result["answerStatus"] == "insufficient_evidence"
  assert result["answer"] is None
  assert generator.calls == []


def test_answer_service_rejects_answer_without_valid_citations():
  generator = FakeAnswerGenerator(LegalAnswerDraft(
    answer="근거 없는 답변",
    citedDocumentIds=[999],
    status=LegalAnswerStatus.ANSWERED,
  ))

  result = LegalAnswerService(generator).answer(
    "계약금을 돌려받을 수 있나요?",
    search_result([source(1)]),
  )

  assert result["success"] is False
  assert result["answerStatus"] == "insufficient_evidence"
  assert result["citations"] == []


def test_answer_service_handles_generation_failure():
  generator = FakeAnswerGenerator(error=RuntimeError("generation failed"))

  result = LegalAnswerService(generator).answer(
    "계약금을 돌려받을 수 있나요?",
    search_result([source(1)]),
  )

  assert result["success"] is False
  assert result["answerStatus"] == "generation_failed"
  assert result["reason"] == "generation_failed"


def test_openai_answer_generator_parses_structured_json():
  completions = FakeCompletions(json.dumps({
    "answer": "민법 제565조에 따른 설명입니다.",
    "citedDocumentIds": [1],
    "status": "answered",
  }))
  client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

  draft = OpenAILegalAnswerGenerator(client=client).generate([
    {"role": "user", "content": "질문"},
  ])

  assert draft.cited_document_ids == [1]
  assert draft.status == LegalAnswerStatus.ANSWERED
  assert completions.requests[0]["model"] == "gpt-5.5"
  assert completions.requests[0]["response_format"]["type"] == "json_schema"
