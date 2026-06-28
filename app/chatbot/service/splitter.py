from __future__ import annotations

import re


SPLIT_PATTERN = re.compile(
  r"\s+(?:그리고|또)\s+"
)


def split_question(question: str) -> list[str]:
  fragments = [fragment.strip() for fragment in SPLIT_PATTERN.split(question.strip())]
  return [fragment for fragment in fragments if fragment]
