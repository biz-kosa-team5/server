from __future__ import annotations

from typing import Any

from .common import clean_text, list_value


def compact_legal_contract_sources(sources: list[dict[str, Any]], *, content_limit: int = 12000) -> list[dict[str, Any]]:
  compacted = []
  for source in sources:
    content = clean_text(source.get("content"))
    compacted.append({
      "lawName": source.get("lawName"),
      "articleNo": source.get("articleNo"),
      "articleTitle": source.get("articleTitle"),
      "paragraphNo": source.get("paragraphNo"),
      "content": content[:content_limit],
      "effectiveDate": source.get("effectiveDate"),
    })
  return compacted


def format_legal_contract_result(result: dict[str, Any]) -> str:
  if result.get("success") is False:
    return format_legal_failure(result)

  sources = [
    source
    for source in list_value(result.get("sources"))
    if isinstance(source, dict)
  ]
  if not sources:
    return clean_text(result.get("summary")) or clean_text(result.get("message")) or "제공된 법령 근거만으로는 확인할 수 없습니다."

  references = [format_legal_reference(source) for source in sources[:3]]
  references = [reference for reference in references if reference]
  summary = clean_text(result.get("summary"))
  if references:
    content_summary = format_content_summary(sources)
    answer = f"검색된 법령 근거로는 {', '.join(references)}가 관련됩니다."
    if content_summary:
      answer += f" 조문 내용상 {content_summary}"
    return f"{answer} 제공된 조문 범위에서만 확인할 수 있습니다."
  if summary:
    return f"{summary} 제공된 조문 범위에서만 확인할 수 있습니다."
  return "검색된 법령 근거가 있지만, 제공된 조문 범위에서만 확인할 수 있습니다."


def format_legal_failure(result: dict[str, Any]) -> str:
  message = clean_text(result.get("message"))
  if message:
    return message
  reason = clean_text(result.get("reason"))
  if reason == "embedding_unavailable":
    return "질문 임베딩을 생성할 수 없어 법령 검색을 실행하지 못했습니다."
  if reason == "no_legal_sources":
    return "질문과 관련된 법령 근거를 찾지 못했습니다."
  return "제공된 법령 근거만으로는 확인할 수 없습니다."


def format_legal_reference(source: dict[str, Any]) -> str:
  law_name = clean_text(source.get("lawName"))
  article_no = format_article_no(source.get("articleNo"))
  article_title = clean_text(source.get("articleTitle"))
  paragraph_no = format_paragraph_no(source.get("paragraphNo"))
  if not law_name and not article_no:
    return ""

  reference = " ".join(part for part in [law_name, article_no] if part)
  if article_title:
    reference += f"({article_title})"
  if paragraph_no:
    reference += f" {paragraph_no}"
  return reference


def format_content_summary(sources: list[dict[str, Any]]) -> str:
  excerpts = [
    format_content_excerpt(source)
    for source in sources[:2]
  ]
  excerpts = [excerpt for excerpt in excerpts if excerpt]
  if not excerpts:
    return ""
  return " ".join(excerpts)


def format_content_excerpt(source: dict[str, Any]) -> str:
  content = normalize_content(clean_text(source.get("content")))
  if not content:
    return ""
  sentences = split_sentences(content)
  excerpt = " ".join(sentences[:2]).strip()
  if not excerpt:
    excerpt = content
  return truncate_text(excerpt, 220)


def normalize_content(content: str) -> str:
  return " ".join(content.split())


def split_sentences(content: str) -> list[str]:
  sentences = []
  start = 0
  for index, char in enumerate(content):
    if char not in ".!?。":
      continue
    sentence = content[start:index + 1].strip()
    if sentence:
      sentences.append(sentence)
    start = index + 1
    if len(sentences) >= 2:
      break
  if not sentences and content:
    sentences.append(content)
  return sentences


def truncate_text(value: str, limit: int) -> str:
  if len(value) <= limit:
    return value
  return value[:limit].rstrip() + "..."


def format_article_no(value: Any) -> str:
  text = clean_text(value)
  if not text:
    return ""
  if text.startswith("제") or text.endswith("조"):
    return text
  return f"제{text}조"


def format_paragraph_no(value: Any) -> str:
  text = clean_text(value)
  if not text:
    return ""
  if text.startswith("제") or text.endswith("항"):
    return text
  return f"{text}항"
