from app.chatbot.service.answer import ChatbotAnswerContext, build_answer_observations, fallback_answer
from app.chatbot.service.answer.formatters.legal_contract import format_legal_contract_result


def source(document_id: int, content: str = "법령 근거") -> dict:
  return {
    "documentId": document_id,
    "lawId": f"LAW-{document_id}",
    "lawName": "민법",
    "articleNo": f"{document_id}",
    "articleTitle": "해약금",
    "paragraphNo": "",
    "content": content,
    "score": 0.7,
    "keywordScore": 0.1,
    "sourceUrl": f"https://example.com/{document_id}",
    "effectiveDate": "2026-06-22",
  }


def legal_context(result: dict) -> ChatbotAnswerContext:
  return ChatbotAnswerContext(
    question="계약금을 돌려받을 수 있나요?",
    success=result.get("success") is True,
    status="success" if result.get("success") else "failed",
    message="질문을 처리했습니다." if result.get("success") else "처리할 수 있는 질문이 없습니다.",
    fragments=[
      {
        "index": 0,
        "text": "계약금을 돌려받을 수 있나요?",
        "status": "handled" if result.get("success") else "not_handled",
        "result": result,
      },
    ],
    result=result,
    executionSummary={
      "total": 1,
      "succeeded": 1 if result.get("success") else 0,
      "failed": 0 if result.get("success") else 1,
    },
  )


def test_legal_observations_use_at_most_seven_sources_and_limit_content():
  context = legal_context({
    "handler": "legal_contract",
    "success": True,
    "question": "계약금을 돌려받을 수 있나요",
    "expandedTerms": ["해약금"],
    "sources": [source(index, content="가" * 12050) for index in range(1, 9)],
    "summary": "관련 근거 조문은 민법 제1조입니다.",
    "message": "관련 법령 근거를 조회했습니다.",
    "answer": "nested answer must be removed",
  })

  observations = build_answer_observations(context)
  single_result = observations["singleResult"]

  assert len(single_result["sources"]) == 7
  assert single_result["sources"][0]["lawName"] == "민법"
  assert single_result["sources"][-1]["articleNo"] == "7"
  assert len(single_result["sources"][0]["content"]) == 12000
  for source_item in single_result["sources"]:
    assert "documentId" not in source_item
    assert "lawId" not in source_item
    assert "score" not in source_item
    assert "vectorScore" not in source_item
    assert "keywordScore" not in source_item
    assert "sourceUrl" not in source_item
  assert "answer" not in single_result
  assert "result" not in observations["rawResponse"]


def test_legal_formatter_combines_source_references_without_internal_fields():
  answer = format_legal_contract_result({
    "handler": "legal_contract",
    "success": True,
    "question": "계약금을 돌려받을 수 있나요",
    "sources": [source(565)],
    "summary": "관련 근거 조문은 민법 제565조입니다.",
    "message": "관련 법령 근거를 조회했습니다.",
  })

  assert "민법 제565조(해약금)" in answer
  assert "법령 근거" in answer
  assert "documentId" not in answer
  assert "score" not in answer
  assert "https://example.com" not in answer
  assert "2026-06-22" not in answer


def test_legal_fallback_uses_handler_formatter_without_llm():
  context = legal_context({
    "handler": "legal_contract",
    "success": True,
    "question": "계약금을 돌려받을 수 있나요",
    "expandedTerms": ["해약금"],
    "sources": [source(565)],
    "summary": "관련 근거 조문은 민법 제565조입니다.",
    "message": "관련 법령 근거를 조회했습니다.",
  })

  assert "민법 제565조(해약금)" in fallback_answer(context)


def test_legal_formatter_handles_no_legal_sources_failure():
  answer = format_legal_contract_result({
    "handler": "legal_contract",
    "success": False,
    "reason": "no_legal_sources",
    "question": "계약금을 돌려받을 수 있나요",
    "expandedTerms": [],
    "sources": [],
    "summary": None,
    "message": "질문과 관련된 법령 근거를 찾지 못했습니다.",
  })

  assert answer == "질문과 관련된 법령 근거를 찾지 못했습니다."
