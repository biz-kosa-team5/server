from __future__ import annotations

from typing import Any

from ..dto.answer import LegalAnswerDraft, LegalAnswerResponse, LegalCitation


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
