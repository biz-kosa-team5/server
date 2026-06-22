from sqlalchemy.orm import Session

from app.chatbot.types import FragmentStatus, Intent
from app.chatbot.service.handler import FeatureSpec, GenericIntentHandler
from app.chatbot.service.registry import FEATURE_REGISTRY


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
  assert set(FEATURE_REGISTRY) == set(Intent)


def test_generic_handler_runs_slots_and_feature_service():
  def extract_slots(question: str):
    return {"question": question}

  def run_feature(_: Session, slots, text: str = ""):
    return {
      "handler": "legal_contract",
      "success": True,
      "question": text,
      "slots": slots,
      "summary": "관련 근거 조문은 민법 제565조입니다.",
    }

  handler = GenericIntentHandler()
  spec = FeatureSpec(Intent.LEGAL_CONTRACT, extract_slots, run_feature, FragmentStatus.HANDLED)

  result = handler.handle(Session(), "매매 계약금 해제 규정 알려줘", spec)

  assert result.status == FragmentStatus.HANDLED
  assert result.slots == {"question": "매매 계약금 해제 규정 알려줘"}
  assert result.result["success"] is True
  assert result.result["handler"] == "legal_contract"
