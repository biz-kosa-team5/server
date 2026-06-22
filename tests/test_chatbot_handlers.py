from sqlalchemy.orm import Session

from app.chatbot.types import FragmentStatus, Intent
from app.chatbot.handler import HANDLER_REGISTRY
from app.chatbot.features.legal_contract import LegalContractHandler


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


def test_handler_registry_covers_every_intent():
  assert set(HANDLER_REGISTRY) == set(Intent)


def test_legal_contract_handler_returns_handled_with_fake_service():
  handler = LegalContractHandler(lambda _: FakeLegalRagService())

  result = handler.handle(Session(), "매매 계약금 해제 규정 알려줘")

  assert result.status == FragmentStatus.HANDLED
  assert result.slots == {}
  assert result.result["success"] is True
  assert result.result["handler"] == "legal_contract"
