from __future__ import annotations

from typing import Any

from app.chatbot.embedding import EmbeddingClient, OpenAIEmbeddingClient, cosine_similarity

from ..dao import LegalRagQueryDao, RankedLawDocument
from ..model import LawDocument


DEFAULT_TOP_K = 5
DEFAULT_MIN_SCORE = 0.55


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
    normalized_question = question.strip()
    expanded_terms = self.expanded_terms(normalized_question)
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

    ranked = self.dao.nearest_law_documents(query_embedding, top_k)
    if ranked is None:
      ranked = python_rank_documents(
        self.dao.list_embedded_law_documents(),
        query_embedding,
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
    terms: list[str] = []
    for mapping in self.dao.matching_term_mappings(question):
      if mapping.legal_term not in terms:
        terms.append(mapping.legal_term)
    return terms

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
  ranked = [
    RankedLawDocument(document=document, score=cosine_similarity(query_embedding, document_embedding(document)))
    for document in documents
  ]
  return sorted(ranked, key=lambda item: (-item.score, item.document.id))[:top_k]


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
    "score": round(item.score, 6),
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
