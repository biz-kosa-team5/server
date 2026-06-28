from __future__ import annotations


QUERY_TERM_SUFFIXES = (
  "에서는", "에게서", "으로", "에서", "에게", "까지", "부터", "처럼", "보다",
  "하면", "해야", "하나요", "인가요", "된", "할", "은", "는", "이", "가",
  "을", "를", "의", "에", "와", "과", "도", "로",
)
QUERY_STOP_WORDS = {
  "반드시", "사항", "언제", "얼마", "어떻게", "무엇", "확인", "하나", "하나요", "있나", "있나요",
}


def build_query_embedding_text(question: str, expanded_terms: list[str]) -> str:
  return "\n".join([
    f"사용자 질문: {question}",
    f"검색 확장어: {', '.join(expanded_terms)}",
  ])


def extract_query_terms(question: str) -> list[str]:
  terms: list[str] = []
  for token in question.split():
    term = strip_query_suffix(token)
    if len(term) < 2 or term in QUERY_STOP_WORDS:
      continue
    terms.append(term)
  return unique_terms(terms)


def strip_query_suffix(token: str) -> str:
  for suffix in QUERY_TERM_SUFFIXES:
    if token.endswith(suffix) and len(token) > len(suffix) + 1:
      return token[:-len(suffix)]
  return token


def longest_terms(terms: list[str]) -> list[str]:
  unique = unique_terms(terms)
  return [
    term
    for term in unique
    if not any(term != other and term in other for other in unique)
  ]


def unique_terms(terms: list[str]) -> list[str]:
  return list(dict.fromkeys(term for term in terms if term))
