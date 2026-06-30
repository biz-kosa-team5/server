from __future__ import annotations

import re


SPLIT_PATTERN = re.compile(
  r"\s+(?:그리고|또)\s+"
)
RECOMMENDATION_SIGNALS = ("추천", "권해", "골라", "조건에 맞는", "후보")
COMPARISON_SIGNALS = ("비교", "차이", "어디가 더", "vs", "VS")
RECOMMENDATION_REFERENCE_SIGNALS = (
  "그 3개",
  "그 세 개",
  "그 후보",
  "그 단지",
  "위 후보",
  "위 단지",
  "위 3개",
  "추천한 단지",
  "추천한 후보",
  "방금 추천",
  "후보들",
)
RECOMMENDATION_REFERENCE_PATTERN = re.compile(
  r"그\s*\d+\s*(?:개|곳|건)"
  r"|위\s*\d+\s*(?:개|곳|건)"
  r"|추천(?:한)?\s*(?:후보|단지)"
)


def split_question(question: str) -> list[str]:
  items = split_items(question.strip())
  if not items:
    return []

  fragments: list[str] = []
  for connector, fragment in items:
    if not fragment:
      continue
    if fragments and connector and should_merge_with_previous(fragments[-1], fragment):
      fragments[-1] = f"{fragments[-1]}{connector}{fragment}".strip()
    else:
      fragments.append(fragment)
  return fragments


def split_items(question: str) -> list[tuple[str | None, str]]:
  if not question:
    return []

  items: list[tuple[str | None, str]] = []
  cursor = 0
  connector: str | None = None
  for match in SPLIT_PATTERN.finditer(question):
    fragment = question[cursor:match.start()].strip()
    items.append((connector, fragment))
    connector = match.group(0)
    cursor = match.end()

  items.append((connector, question[cursor:].strip()))
  return items


def should_merge_with_previous(previous: str, current: str) -> bool:
  return (
    has_recommendation_signal(previous)
    and has_comparison_signal(current)
    and has_recommendation_reference_signal(current)
  )


def has_recommendation_signal(text: str) -> bool:
  return any(signal in text for signal in RECOMMENDATION_SIGNALS)


def has_comparison_signal(text: str) -> bool:
  return any(signal in text for signal in COMPARISON_SIGNALS)


def has_recommendation_reference_signal(text: str) -> bool:
  return (
    any(signal in text for signal in RECOMMENDATION_REFERENCE_SIGNALS)
    or RECOMMENDATION_REFERENCE_PATTERN.search(text) is not None
  )
