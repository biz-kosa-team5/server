from __future__ import annotations

from app.chatbot.embedding import cosine_similarity

from ..dao import RankedLawDocument
from ..model import LawDocument
from .query_intent import LegalQueryIntent


MAX_KEYWORD_SCORE = 0.25
MAX_PRIMARY_KEYWORD_SCORE = 0.20
MAX_EXPANDED_KEYWORD_SCORE = 0.04
MAX_DOCUMENTS_PER_LAW_IN_TOP_RESULTS = 2
DIVERSITY_SCORE_TOLERANCE = 0.05
SPECIAL_CONTEXT_PENALTY = 0.04
TAX_SPECIAL_CONTEXT_PENALTY = 0.07
MAX_INTENT_FOCUS_SCORE = 0.08
BROAD_LOW_VALUE_PENALTY = 0.06
REGISTRATION_SPECIAL_CONTEXT_PENALTY = 0.08

LOW_SIGNAL_PRIMARY_TERMS = {"등기부"}
HIGH_SIGNAL_EXPANDED_TERMS = {
  "가압류",
  "근저당권",
  "대금 지급",
  "대항력",
  "양도소득세",
  "매매의 의의",
  "소유권 이전등기",
  "임차권등기",
  "저당권",
  "취득세",
  "증여",
  "증여세",
}
SPECIAL_CONTEXT_TERMS = {
  "부동산매매업자",
  "비사업용 토지",
  "일부이전",
  "일부 이전",
  "특례",
}
SPECIAL_CONTEXT_USER_TERMS = {
  "부동산매매업자",
  "매매업자",
  "사업자",
  "비사업용",
  "일부이전",
  "일부 이전",
  "지분",
  "특례",
}
BROAD_FOCUS_TERMS = {
  "매매의 의의",
  "해약금",
  "부동산 거래의 신고",
  "거래계약서의 작성",
  "거래가액과 매매목록",
  "소유권 이전등기",
  "등기신청인",
  "취득세",
  "양도소득",
  "중개대상물",
  "대항력",
  "저당권의 등기사항",
}
CHECKLIST_FOCUS_TERMS = {
  "매매의 의의",
  "거래계약서의 작성",
  "거래가액과 매매목록",
  "해약금",
  "매매계약의 비용",
  "중개대상물",
  "저당권의 등기사항",
}
PRE_CONTRACT_CHECK_FOCUS_TERMS = {
  "중개대상물의 확인",
  "중개대상물",
  "등기사항증명서",
  "권리관계",
  "거래 또는 이용 제한",
  "부동산 거래의 신고",
  "거래가액과 매매목록",
  "저당권의 등기사항",
  "대항력",
}
LEASE_FOCUS_TERMS = {
  "대항력",
  "임차주택의 양수인",
  "임대인의 지위를 승계",
  "주택의 인도",
  "주민등록",
  "보증금의 회수",
  "보증금 반환",
  "우선변제권",
}
RISK_FOCUS_TERMS = {
  "등기할 수 있는 권리",
  "처분의 제한",
  "가등기",
  "저당권의 등기사항",
  "저당권설정등기",
  "근저당권",
  "압류",
  "가압류",
  "가처분",
  "경매개시",
  "전세권",
  "임차권등기",
  "채권최고액",
}
FALSE_PRICE_FOCUS_TERMS = {
  "부동산 거래의 신고",
  "실제 거래가격",
  "거래계약서의 작성",
  "거래내용을 거짓",
  "서로 다른 둘 이상의 거래계약서",
  "양도소득세 비과세 또는 감면의 배제",
  "거래가액과 매매목록",
}
BROAD_LOW_VALUE_ARTICLE_TITLES = {
  "정의",
  "자료 등 종합관리",
  "부동산정책 관련 자료 등 종합관리",
  "소유자 등의 확인",
  "신탁주택 관련 수탁자의 물적납세의무",
  "부동산 등의 평가",
}
REGISTRATION_SPECIAL_TITLES = {
  "소유권의 일부이전",
  "소유권의 일부이전등기 신청",
  "저당권 이전등기의 신청",
  "채권일부의 양도 또는 대위변제로 인한 저당권 일부이전등기의 등기사항",
  "전세금반환채권의 일부양도에 따른 전세권 일부이전등기",
}


def python_rank_documents(
  documents: list[LawDocument],
  query_embedding: list[float],
  top_k: int,
) -> list[RankedLawDocument]:
  ranked = []
  for document in documents:
    vector_score = float(cosine_similarity(query_embedding, document_embedding(document)))
    ranked.append(RankedLawDocument(
      document=document,
      score=vector_score,
      vector_score=vector_score,
    ))
  return sorted(ranked, key=lambda item: (-item.score, item.document.id))[:top_k]


def hybrid_rank_documents(
  vector_ranked: list[RankedLawDocument],
  keyword_documents: list[LawDocument],
  query_embedding: list[float],
  primary_terms: list[str],
  expanded_terms: list[str],
  intents: list[LegalQueryIntent] | None,
  top_k: int,
) -> list[RankedLawDocument]:
  candidates = {item.document.id: item for item in vector_ranked}
  for document in keyword_documents:
    if document.id in candidates:
      continue
    vector_score = float(cosine_similarity(query_embedding, document_embedding(document)))
    candidates[document.id] = RankedLawDocument(
      document=document,
      score=vector_score,
      vector_score=vector_score,
    )

  reranked = []
  for item in candidates.values():
    keyword_score = document_keyword_score(item.document, primary_terms, expanded_terms)
    intent_focus_score = document_intent_focus_score(item.document, intents or [])
    penalty = special_context_penalty(item.document, primary_terms, intents or [])
    penalty += broad_low_value_penalty(item.document, intents or [])
    reranked.append(RankedLawDocument(
      document=item.document,
      score=float(max(0.0, min(1.0, item.vector_score + keyword_score + intent_focus_score) - penalty)),
      vector_score=float(item.vector_score),
      keyword_score=round(keyword_score + intent_focus_score, 6),
    ))
  ranked = sorted(reranked, key=lambda item: (-item.score, -item.vector_score, item.document.id))
  return diversify_ranked_documents(ranked, top_k)


def diversify_ranked_documents(
  ranked: list[RankedLawDocument],
  top_k: int,
) -> list[RankedLawDocument]:
  selected: list[RankedLawDocument] = []
  selected_ids: set[int] = set()
  law_counts: dict[str, int] = {}

  for item in ranked:
    law_name = item.document.law_name
    if (
      law_counts.get(law_name, 0) >= MAX_DOCUMENTS_PER_LAW_IN_TOP_RESULTS
      and has_competitive_diverse_candidate(item, ranked, selected_ids, law_counts)
    ):
      continue
    selected.append(item)
    selected_ids.add(item.document.id)
    law_counts[law_name] = law_counts.get(law_name, 0) + 1
    if len(selected) >= top_k:
      return selected

  for item in ranked:
    if item.document.id in selected_ids:
      continue
    selected.append(item)
    if len(selected) >= top_k:
      break

  return selected


def has_competitive_diverse_candidate(
  item: RankedLawDocument,
  ranked: list[RankedLawDocument],
  selected_ids: set[int],
  law_counts: dict[str, int],
) -> bool:
  minimum_competitive_score = item.score - DIVERSITY_SCORE_TOLERANCE
  for candidate in ranked:
    if candidate.document.id in selected_ids or candidate.document.id == item.document.id:
      continue
    if candidate.score < minimum_competitive_score:
      return False
    if law_counts.get(candidate.document.law_name, 0) < MAX_DOCUMENTS_PER_LAW_IN_TOP_RESULTS:
      return True
  return False


def document_keyword_score(
  document: LawDocument,
  primary_terms: list[str],
  expanded_terms: list[str],
) -> float:
  primary_score = sum(
    term_keyword_score(document, term, primary_term_weight(term))
    for term in primary_terms
  )
  expanded_score = sum(
    term_keyword_score(document, term, expanded_term_weight(term))
    for term in expanded_terms
    if term not in primary_terms
  )
  return round(min(
    MAX_KEYWORD_SCORE,
    min(MAX_PRIMARY_KEYWORD_SCORE, primary_score)
    + min(MAX_EXPANDED_KEYWORD_SCORE, expanded_score),
  ), 6)


def term_keyword_score(document: LawDocument, term: str, weight: float) -> float:
  normalized_term = term.casefold().strip()
  if not normalized_term:
    return 0.0

  score = 0.0
  if normalized_term in document.law_name.casefold():
    score += 0.12
  if normalized_term in (document.article_title or "").casefold():
    score += 0.10
  if normalized_term in document.content.casefold():
    score += 0.04
  return score * weight


def primary_term_weight(term: str) -> float:
  if term.casefold().strip() in LOW_SIGNAL_PRIMARY_TERMS:
    return 0.55
  return 1.0


def expanded_term_weight(term: str) -> float:
  if term.casefold().strip() in HIGH_SIGNAL_EXPANDED_TERMS:
    return 0.30
  return 0.15


def document_intent_focus_score(
  document: LawDocument,
  intents: list[LegalQueryIntent],
) -> float:
  score = 0.0
  title = (document.article_title or "").casefold()
  content = (document.content or "").casefold()
  if LegalQueryIntent.BROAD in intents:
    score += focus_term_score(title, content, BROAD_FOCUS_TERMS, title_score=0.05, content_score=0.02)
  if LegalQueryIntent.CHECKLIST in intents:
    score += focus_term_score(title, content, CHECKLIST_FOCUS_TERMS, title_score=0.06, content_score=0.02)
  if LegalQueryIntent.PRE_CONTRACT_CHECK in intents:
    score += focus_term_score(title, content, PRE_CONTRACT_CHECK_FOCUS_TERMS, title_score=0.07, content_score=0.03)
  if LegalQueryIntent.LEASE in intents:
    score += focus_term_score(title, content, LEASE_FOCUS_TERMS, title_score=0.07, content_score=0.04)
  if LegalQueryIntent.RISK in intents:
    score += focus_term_score(title, content, RISK_FOCUS_TERMS, title_score=0.06, content_score=0.02)
  if LegalQueryIntent.FALSE_PRICE in intents:
    score += focus_term_score(title, content, FALSE_PRICE_FOCUS_TERMS, title_score=0.07, content_score=0.03)
  if LegalQueryIntent.TAX in intents:
    score += tax_focus_score(title, content)
  return round(min(MAX_INTENT_FOCUS_SCORE, score), 6)


def focus_term_score(
  title: str,
  content: str,
  terms: set[str],
  title_score: float,
  content_score: float,
) -> float:
  for term in terms:
    normalized = term.casefold()
    if normalized in title:
      return title_score
  for term in terms:
    if term.casefold() in content:
      return content_score
  return 0.0


def tax_focus_score(title: str, content: str) -> float:
  score = 0.0
  if "취득세" in title or "양도소득세" in title or "양도소득" in title:
    score += 0.08
  elif "주택 취득" in title or "취득 중과" in title:
    score += 0.07
  elif "취득세" in content or "양도소득세" in content:
    score += 0.04
  return score


def special_context_penalty(
  document: LawDocument,
  primary_terms: list[str],
  intents: list[LegalQueryIntent],
) -> float:
  if not should_apply_special_context_penalty(primary_terms, intents):
    return 0.0
  if document_contains_special_context(document):
    if LegalQueryIntent.REGISTRATION in intents and document_title_in(document, REGISTRATION_SPECIAL_TITLES):
      return REGISTRATION_SPECIAL_CONTEXT_PENALTY
    if LegalQueryIntent.TAX in intents and document_contains_any(document, {"부동산매매업자", "매매업자"}):
      return TAX_SPECIAL_CONTEXT_PENALTY
    return SPECIAL_CONTEXT_PENALTY
  return 0.0


def broad_low_value_penalty(
  document: LawDocument,
  intents: list[LegalQueryIntent],
) -> float:
  if LegalQueryIntent.BROAD not in intents:
    return 0.0
  if document_title_in(document, BROAD_LOW_VALUE_ARTICLE_TITLES):
    return BROAD_LOW_VALUE_PENALTY
  return 0.0


def should_apply_special_context_penalty(
  primary_terms: list[str],
  intents: list[LegalQueryIntent],
) -> bool:
  if LegalQueryIntent.GENERAL in intents and len(intents) == 1:
    return False
  normalized_terms = " ".join(primary_terms).casefold()
  return not any(term.casefold() in normalized_terms for term in SPECIAL_CONTEXT_USER_TERMS)


def document_contains_special_context(document: LawDocument) -> bool:
  return document_contains_any(document, SPECIAL_CONTEXT_TERMS)


def document_contains_any(document: LawDocument, terms: set[str]) -> bool:
  text = " ".join([
    document.law_name or "",
    document.article_title or "",
    document.content or "",
  ]).casefold()
  return any(term.casefold() in text for term in terms)


def document_title_in(document: LawDocument, titles: set[str]) -> bool:
  title = (document.article_title or "").casefold().strip()
  return any(term.casefold() == title for term in titles)


def document_embedding(document: LawDocument) -> list[float]:
  if document.embedding is None:
    return []
  return list(document.embedding)
