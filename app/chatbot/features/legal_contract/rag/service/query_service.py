from __future__ import annotations

from typing import Any

from app.chatbot.embedding import EmbeddingClient, OpenAIEmbeddingClient, cosine_similarity
from app.chatbot.features.legal_contract.normalization import normalize_query

from ..dao import LegalRagQueryDao, RankedLawDocument
from ..model import LawDocument


DEFAULT_TOP_K = 5
DEFAULT_MIN_SCORE = 0.45
DEFAULT_CANDIDATE_K = 50
MAX_KEYWORD_SCORE = 0.25
MAX_PRIMARY_KEYWORD_SCORE = 0.20
MAX_EXPANDED_KEYWORD_SCORE = 0.05

QUERY_TERM_SUFFIXES = (
  "에서는", "에게서", "으로", "에서", "에게", "까지", "부터", "처럼", "보다",
  "하면", "해야", "하나요", "인가요", "된", "할", "은", "는", "이", "가",
  "을", "를", "의", "에", "와", "과", "도", "로",
)
QUERY_STOP_WORDS = {
  "반드시", "사항", "언제", "얼마", "어떻게", "무엇", "확인", "하나", "하나요", "있나", "있나요",
}


class LegalRagQueryService:
  def __init__(
    self,
    dao: LegalRagQueryDao,
    client: EmbeddingClient | None = None,
    min_score: float = DEFAULT_MIN_SCORE,
  ):
    self.dao = dao
    self.client = client
    self.min_score = min_score

  def query(self, question: str, top_k: int = DEFAULT_TOP_K) -> dict[str, Any]:
    normalized_question = normalize_query(question)
    mappings = self.dao.matching_term_mappings(normalized_question)
    daily_terms = unique_terms([mapping.daily_term for mapping in mappings])
    expanded_terms = unique_terms([mapping.legal_term for mapping in mappings])
    primary_terms = longest_terms(extract_query_terms(normalized_question) + daily_terms)
    client = self.embedding_client()
    if client is None:
      return failure_result(
        normalized_question,
        expanded_terms,
        "embedding_unavailable",
        "질문 임베딩을 생성할 수 없어 법령 검색을 실행하지 못했습니다.",
      )

    try:
      embedding_text = client.prepare_text(build_query_embedding_text(normalized_question, expanded_terms))
      query_embedding = client.embed([embedding_text])[0]
    except Exception:
      return failure_result(
        normalized_question,
        expanded_terms,
        "embedding_unavailable",
        "질문 임베딩을 생성할 수 없어 법령 검색을 실행하지 못했습니다.",
      )

    candidate_k = max(DEFAULT_CANDIDATE_K, top_k * 10)
    ranked = self.dao.nearest_law_documents(query_embedding, candidate_k)
    if ranked is None:
      ranked = python_rank_documents(
        self.dao.list_embedded_law_documents(),
        query_embedding,
        candidate_k,
      )
    ranked = hybrid_rank_documents(
      ranked,
      self.dao.keyword_law_documents(primary_terms + expanded_terms),
      query_embedding,
      primary_terms,
      expanded_terms,
      top_k,
    )

    sources = [
      source_item(item)
      for item in ranked
      if item.score >= self.min_score
    ]
    if not sources:
      return failure_result(
        normalized_question,
        expanded_terms,
        "no_legal_sources",
        "질문과 관련된 법령 근거를 찾지 못했습니다.",
      )

    return {
      "handler": "legal_contract",
      "success": True,
      "question": normalized_question,
      "expandedTerms": expanded_terms,
      "sources": sources,
      "summary": summarize_sources(sources),
      "message": "관련 법령 근거를 조회했습니다.",
    }

  def expanded_terms(self, question: str) -> list[str]:
    return unique_terms([
      mapping.legal_term
      for mapping in self.dao.matching_term_mappings(question)
    ])

  def embedding_client(self) -> EmbeddingClient | None:
    if self.client is not None:
      return self.client
    try:
      return OpenAIEmbeddingClient()
    except ValueError:
      return None


def build_query_embedding_text(question: str, expanded_terms: list[str]) -> str:
  return "\n".join([
    f"사용자 질문: {question}",
    f"검색 확장어: {', '.join(expanded_terms)}",
  ])


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
    reranked.append(RankedLawDocument(
      document=item.document,
      score=float(min(1.0, item.vector_score + keyword_score)),
      vector_score=float(item.vector_score),
      keyword_score=keyword_score,
    ))
  return sorted(reranked, key=lambda item: (-item.score, -item.vector_score, item.document.id))[:top_k]


def document_keyword_score(
  document: LawDocument,
  primary_terms: list[str],
  expanded_terms: list[str],
) -> float:
  primary_score = sum(
    term_keyword_score(document, term, 1.0)
    for term in primary_terms
  )
  expanded_score = sum(
    term_keyword_score(document, term, 0.25)
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


def unique_terms(terms: list[str]) -> list[str]:
  return list(dict.fromkeys(term for term in terms if term))


def extract_query_terms(question: str) -> list[str]:
  terms: list[str] = []
  for token in question.split():
    term = token
    for suffix in QUERY_TERM_SUFFIXES:
      if term.endswith(suffix) and len(term) > len(suffix) + 1:
        term = term[:-len(suffix)]
        break
    if len(term) < 2 or term in QUERY_STOP_WORDS:
      continue
    terms.append(term)
  return unique_terms(terms)


def longest_terms(terms: list[str]) -> list[str]:
  unique = unique_terms(terms)
  return [
    term
    for term in unique
    if not any(term != other and term in other for other in unique)
  ]


def document_embedding(document: LawDocument) -> list[float]:
  if document.embedding is None:
    return []
  return list(document.embedding)


def source_item(item: RankedLawDocument) -> dict[str, Any]:
  document = item.document
  return {
    "documentId": document.id,
    "lawId": document.law_id,
    "lawName": document.law_name,
    "articleNo": document.article_no,
    "articleTitle": document.article_title,
    "paragraphNo": document.paragraph_no,
    "content": document.content,
    "score": round(float(item.score), 6),
    "vectorScore": round(float(item.vector_score), 6),
    "keywordScore": round(float(item.keyword_score), 6),
    "sourceUrl": document.source_url,
    "effectiveDate": document.effective_date.isoformat(),
  }


def summarize_sources(sources: list[dict[str, Any]]) -> str:
  references = [
    f"{source['lawName']} {source['articleNo']}"
    for source in sources
  ]
  return f"관련 근거 조문은 {', '.join(references)}입니다."


def failure_result(
  question: str,
  expanded_terms: list[str],
  reason: str,
  message: str,
) -> dict[str, Any]:
  return {
    "handler": "legal_contract",
    "success": False,
    "reason": reason,
    "question": question,
    "expandedTerms": expanded_terms,
    "sources": [],
    "summary": None,
    "message": message,
  }
