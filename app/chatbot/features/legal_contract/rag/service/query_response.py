from __future__ import annotations

from typing import Any

from ..dao import RankedLawDocument


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


def success_result(
  question: str,
  expanded_terms: list[str],
  sources: list[dict[str, Any]],
) -> dict[str, Any]:
  return {
    "handler": "legal_contract",
    "success": True,
    "question": question,
    "expandedTerms": expanded_terms,
    "sources": sources,
    "summary": summarize_sources(sources),
    "message": "관련 법령 근거를 조회했습니다.",
  }


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
