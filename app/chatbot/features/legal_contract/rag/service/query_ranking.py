from __future__ import annotations

from app.chatbot.embedding import cosine_similarity

from ..dao import RankedLawDocument
from ..model import LawDocument


MAX_KEYWORD_SCORE = 0.25
MAX_PRIMARY_KEYWORD_SCORE = 0.20
MAX_EXPANDED_KEYWORD_SCORE = 0.05


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


def document_embedding(document: LawDocument) -> list[float]:
  if document.embedding is None:
    return []
  return list(document.embedding)
