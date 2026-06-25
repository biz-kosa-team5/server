from app.chatbot.features.legal_contract.rag.dao import RankedLawDocument
from app.chatbot.features.legal_contract.rag.model import LawDocument
from app.chatbot.features.legal_contract.rag.service.query_intent import LegalQueryIntent
from app.chatbot.features.legal_contract.rag.service.query_ranking import (
  BROAD_LOW_VALUE_PENALTY,
  REGISTRATION_SPECIAL_CONTEXT_PENALTY,
  TAX_SPECIAL_CONTEXT_PENALTY,
  broad_low_value_penalty,
  document_intent_focus_score,
  diversify_ranked_documents,
  special_context_penalty,
)


def law_document(
  document_id: int,
  law_name: str,
  article_title: str = "테스트 조문",
  content: str = "테스트 내용",
) -> LawDocument:
  return LawDocument(
    id=document_id,
    law_id=f"LAW-{document_id}",
    law_name=law_name,
    article_no=f"제{document_id}조",
    article_title=article_title,
    paragraph_no="",
    content=content,
    embedding=[1.0, 0.0],
  )


def ranked_document(document_id: int, law_name: str, score: float) -> RankedLawDocument:
  return RankedLawDocument(
    document=law_document(document_id, law_name),
    score=score,
    vector_score=score,
  )


def test_diversify_ranked_documents_limits_same_law_in_top_results():
  ranked = [
    ranked_document(1, "민법", 0.90),
    ranked_document(2, "민법", 0.89),
    ranked_document(3, "민법", 0.88),
    ranked_document(4, "부동산등기법", 0.87),
    ranked_document(5, "공인중개사법", 0.86),
  ]

  selected = diversify_ranked_documents(ranked, top_k=5)

  assert [item.document.id for item in selected] == [1, 2, 4, 5, 3]


def test_diversify_ranked_documents_fills_when_only_one_law_is_available():
  ranked = [
    ranked_document(1, "민법", 0.90),
    ranked_document(2, "민법", 0.89),
    ranked_document(3, "민법", 0.88),
  ]

  selected = diversify_ranked_documents(ranked, top_k=3)

  assert [item.document.id for item in selected] == [1, 2, 3]


def test_diversify_ranked_documents_keeps_same_law_when_alternatives_are_weak():
  ranked = [
    ranked_document(1, "민법", 0.90),
    ranked_document(2, "민법", 0.89),
    ranked_document(3, "민법", 0.80),
    ranked_document(4, "공인중개사법", 0.60),
    ranked_document(5, "부동산등기법", 0.59),
  ]

  selected = diversify_ranked_documents(ranked, top_k=5)

  assert [item.document.id for item in selected] == [1, 2, 3, 4, 5]


def test_special_context_penalty_lowers_special_article_for_general_tax_question():
  document = law_document(
    10,
    "소득세법",
    article_title="부동산매매업자에 대한 세액 계산의 특례",
    content="부동산매매업자의 주택등매매차익에 대한 세액 계산 특례",
  )

  penalty = special_context_penalty(
    document,
    primary_terms=["아파트", "매매", "세금"],
    intents=[LegalQueryIntent.TAX],
  )

  assert penalty == TAX_SPECIAL_CONTEXT_PENALTY


def test_special_context_penalty_is_disabled_when_user_mentions_special_context():
  document = law_document(
    10,
    "소득세법",
    article_title="부동산매매업자에 대한 세액 계산의 특례",
    content="부동산매매업자의 주택등매매차익에 대한 세액 계산 특례",
  )

  penalty = special_context_penalty(
    document,
    primary_terms=["부동산매매업자", "세금"],
    intents=[LegalQueryIntent.TAX],
  )

  assert penalty == 0


def test_tax_intent_focus_score_boosts_direct_tax_article_titles():
  document = law_document(
    20,
    "소득세법",
    article_title="양도소득세액의 감면",
    content="양도소득세 감면 규정",
  )

  score = document_intent_focus_score(document, [LegalQueryIntent.TAX])

  assert score > 0


def test_tax_intent_focus_score_does_not_apply_to_non_tax_intent():
  document = law_document(
    20,
    "소득세법",
    article_title="양도소득세액의 감면",
    content="양도소득세 감면 규정",
  )

  score = document_intent_focus_score(document, [LegalQueryIntent.CONTRACT])

  assert score == 0


def test_broad_intent_focus_score_boosts_core_broad_topics():
  document = law_document(
    30,
    "부동산 거래신고 등에 관한 법률",
    article_title="부동산 거래의 신고",
    content="부동산 매매계약 신고 규정",
  )

  score = document_intent_focus_score(document, [LegalQueryIntent.BROAD])

  assert score > 0


def test_lease_intent_focus_score_boosts_landlord_status_succession():
  document = law_document(
    31,
    "주택임대차보호법",
    article_title="대항력 등",
    content="임차주택의 양수인은 임대인의 지위를 승계한 것으로 본다.",
  )

  score = document_intent_focus_score(document, [LegalQueryIntent.LEASE])

  assert score > 0


def test_pre_contract_check_focus_score_boosts_broker_explanation_duty():
  document = law_document(
    32,
    "공인중개사법",
    article_title="중개대상물의 확인ㆍ설명",
    content="권리관계와 거래 또는 이용 제한사항을 설명한다.",
  )

  score = document_intent_focus_score(document, [LegalQueryIntent.PRE_CONTRACT_CHECK])

  assert score > 0


def test_false_price_focus_score_boosts_false_contract_amount_articles():
  document = law_document(
    33,
    "공인중개사법",
    article_title="거래계약서의 작성 등",
    content="거래금액 등 거래내용을 거짓으로 기재하면 안 된다.",
  )

  score = document_intent_focus_score(document, [LegalQueryIntent.FALSE_PRICE])

  assert score > 0


def test_broad_low_value_penalty_lowers_definition_articles():
  document = law_document(
    40,
    "부동산 거래신고 등에 관한 법률",
    article_title="정의",
    content="용어 정의",
  )

  penalty = broad_low_value_penalty(document, [LegalQueryIntent.BROAD])

  assert penalty == BROAD_LOW_VALUE_PENALTY


def test_registration_penalty_lowers_partial_transfer_articles():
  document = law_document(
    50,
    "부동산등기법",
    article_title="소유권의 일부이전",
    content="소유권 일부이전 등기",
  )

  penalty = special_context_penalty(
    document,
    primary_terms=["소유권", "이전등기"],
    intents=[LegalQueryIntent.REGISTRATION],
  )

  assert penalty == REGISTRATION_SPECIAL_CONTEXT_PENALTY
