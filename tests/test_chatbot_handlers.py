from sqlalchemy.orm import Session

from app.chatbot.features.legal_contract.service import run_legal_contract
from app.chatbot.features.legal_contract.slots import extract_legal_contract_slots


class FakeLegalRagService:
  def query(self, question: str, top_k: int = 5):
    return {
      "handler": "legal_contract",
      "success": True,
      "question": question,
      "expandedTerms": ["해약금"],
      "sources": [],
      "summary": "관련 근거 조문은 민법 제565조입니다.",
      "message": "관련 법령 근거를 조회했습니다.",
    }


def test_legal_contract_slots_keep_original_query():
  question = "  계약금을 돌려받을 수 있나요?  "

  assert extract_legal_contract_slots(question) == {
    "original_query": question,
    "normalized_query": "계약금을 돌려받을 수 있나요",
    "expanded_terms": [],
  }


def test_legal_contract_service_fills_expanded_terms_in_slots():
  slots = extract_legal_contract_slots("계약금을 돌려받을 수 있나요?")

  result = run_legal_contract(
    Session(),
    slots,
    service_factory=lambda _: FakeLegalRagService(),
  )

  assert slots["original_query"] == "계약금을 돌려받을 수 있나요?"
  assert slots["normalized_query"] == "계약금을 돌려받을 수 있나요"
  assert slots["expanded_terms"] == result["expandedTerms"]
  assert result["question"] == slots["original_query"]
  assert result["answerStatus"] == "insufficient_evidence"
