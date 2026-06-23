from __future__ import annotations

from typing import Any

from app.chatbot.embedding import EmbeddingClient, OpenAIEmbeddingClient
from app.chatbot.features.legal_contract.normalization import normalize_query

from ..dao import LegalRagQueryDao
from .query_ranking import hybrid_rank_documents, python_rank_documents
from .query_response import failure_result, source_item, success_result
from .query_text import (
  build_query_embedding_text,
  extract_query_terms,
  longest_terms,
  unique_terms,
)


DEFAULT_TOP_K = 5
DEFAULT_MIN_SCORE = 0.45
DEFAULT_CANDIDATE_K = 50


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

    return success_result(normalized_question, expanded_terms, sources)

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
