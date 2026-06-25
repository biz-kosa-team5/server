from app.chatbot.features.legal_contract.rag.service.query_expansion import (
  build_intent_expansion_terms,
)
from app.chatbot.features.legal_contract.rag.service.query_intent import (
  LegalQueryIntent,
  detect_query_intents,
)


def test_detect_query_intents_for_tax_question():
  intents = detect_query_intents("아파트 매매 시 세금 책정 관련 법을 알려줘")

  assert LegalQueryIntent.TAX in intents


def test_detect_query_intents_for_registration_question():
  intents = detect_query_intents("명의 이전은 어떤 법과 관련 있어")

  assert LegalQueryIntent.REGISTRATION in intents


def test_detect_query_intents_for_risk_question():
  intents = detect_query_intents("등기부에서 빚 잡힌 집인지 보려면 뭘 봐야 해")

  assert LegalQueryIntent.RISK in intents
  assert LegalQueryIntent.BROAD not in intents


def test_detect_query_intents_for_lease_question():
  intents = detect_query_intents("세입자 있는 집을 사도 괜찮아")

  assert LegalQueryIntent.LEASE in intents


def test_detect_query_intents_for_lease_deposit_question():
  intents = detect_query_intents("전세 낀 아파트를 사면 보증금은 누가 돌려줘야 해")

  assert LegalQueryIntent.LEASE in intents


def test_detect_query_intents_for_broad_question():
  intents = detect_query_intents("집을 살 때 알아야 할 법이 있을까")

  assert LegalQueryIntent.BROAD in intents


def test_detect_query_intents_for_checklist_question():
  intents = detect_query_intents("매매 계약서에서 중요하게 볼 부분은 어디야")

  assert LegalQueryIntent.CHECKLIST in intents


def test_detect_query_intents_for_pre_contract_check_question():
  intents = detect_query_intents("아파트 살 때 계약 전에 꼭 확인해야 할 법적 사항은 뭐야")

  assert LegalQueryIntent.PRE_CONTRACT_CHECK in intents


def test_detect_query_intents_for_false_price_question():
  intents = detect_query_intents("집값을 실제보다 낮게 계약서에 쓰면 문제가 있어")

  assert LegalQueryIntent.FALSE_PRICE in intents


def test_intent_expansion_uses_concepts_not_article_numbers():
  terms = build_intent_expansion_terms([LegalQueryIntent.TAX, LegalQueryIntent.REGISTRATION])

  assert "취득세" in terms
  assert "소유권 이전등기" in terms
  assert not any("제" in term and "조" in term for term in terms)
