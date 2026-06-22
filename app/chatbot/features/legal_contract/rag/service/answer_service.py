from __future__ import annotations

from typing import Any

from ..dto.answer import (
  LegalAnswerDraft,
  LegalAnswerResponse,
  LegalAnswerStatus,
  LegalCitation,
)
from .answer_generator import LegalAnswerGenerator
from .answer_prompt import MAX_ANSWER_SOURCES, build_legal_answer_messages


class LegalAnswerService:
  def __init__(self, generator: LegalAnswerGenerator):
    self.generator = generator

  def answer(
    self,
    question: str,
    search_result: dict[str, Any],
  ) -> dict[str, Any]:
    sources = list(search_result.get("sources", []))[:MAX_ANSWER_SOURCES]
    expanded_terms = list(search_result.get("expandedTerms", []))
    retrieval_score = top_retrieval_score(sources)

    if not search_result.get("success") or not sources:
      return response_dict(LegalAnswerResponse(
        success=False,
        question=question,
        expandedTerms=expanded_terms,
        answer=None,
        answerStatus=LegalAnswerStatus.INSUFFICIENT_EVIDENCE,
        citations=[],
        sources=sources,
        retrievalScore=retrieval_score,
        reason=search_result.get("reason", "insufficient_evidence"),
        message="답변을 생성할 충분한 법령 근거를 찾지 못했습니다.",
      ))

    try:
      draft = self.generator.generate(build_legal_answer_messages(question, sources))
    except Exception:
      return response_dict(LegalAnswerResponse(
        success=False,
        question=question,
        expandedTerms=expanded_terms,
        answer=None,
        answerStatus=LegalAnswerStatus.GENERATION_FAILED,
        citations=[],
        sources=sources,
        retrievalScore=retrieval_score,
        reason="generation_failed",
        message="법률 답변을 생성하지 못했습니다.",
      ))

    citations = validated_citations(draft, sources)
    if draft.status != LegalAnswerStatus.ANSWERED or not draft.answer or not citations:
      return response_dict(LegalAnswerResponse(
        success=False,
        question=question,
        expandedTerms=expanded_terms,
        answer=None,
        answerStatus=LegalAnswerStatus.INSUFFICIENT_EVIDENCE,
        citations=[],
        sources=sources,
        retrievalScore=retrieval_score,
        reason="insufficient_evidence",
        message="검색된 법령만으로 신뢰할 수 있는 답변을 생성하지 못했습니다.",
      ))

    return response_dict(LegalAnswerResponse(
      success=True,
      question=question,
      expandedTerms=expanded_terms,
      answer=answer_with_citations(draft.answer.strip(), citations),
      answerStatus=LegalAnswerStatus.ANSWERED,
      citations=citations,
      sources=sources,
      retrievalScore=retrieval_score,
      message="검색된 법령 근거를 바탕으로 답변했습니다.",
    ))


def validated_citations(
  draft: LegalAnswerDraft,
  sources: list[dict[str, Any]],
) -> list[LegalCitation]:
  sources_by_id = {source["documentId"]: source for source in sources}
  citations = []
  seen_ids: set[int] = set()
  for document_id in draft.cited_document_ids:
    source = sources_by_id.get(document_id)
    if source is None or document_id in seen_ids:
      continue
    seen_ids.add(document_id)
    citations.append(LegalCitation(
      documentId=document_id,
      lawName=source["lawName"],
      articleNo=source["articleNo"],
      articleTitle=source.get("articleTitle"),
      paragraphNo=source.get("paragraphNo", ""),
      sourceUrl=source.get("sourceUrl"),
      effectiveDate=source["effectiveDate"],
    ))
  return citations


def top_retrieval_score(sources: list[dict[str, Any]]) -> float | None:
  if not sources:
    return None
  return round(float(sources[0]["score"]), 6)


def answer_with_citations(answer: str, citations: list[LegalCitation]) -> str:
  lines = [answer.rstrip(), "", "출처"]
  for citation in citations:
    article = citation.article_no
    if citation.article_title:
      article = f"{article}({citation.article_title})"
    if citation.paragraph_no:
      article = f"{article} {citation.paragraph_no}"

    source = (
      f"- [{citation.document_id}] {citation.law_name} {article}"
      f" (시행일: {citation.effective_date})"
    )
    lines.append(source)
    if citation.source_url:
      lines.append(f"  {citation.source_url}")
  return "\n".join(lines)


def response_dict(response: LegalAnswerResponse) -> dict[str, Any]:
  return response.model_dump(mode="json", by_alias=True)
