from __future__ import annotations

import re


SPLIT_PATTERN = re.compile(
  r"\s*(?:그리고|또|추천하고|조회하고|알려주고|찾아주고|해주고|추천해주고|찾아보고)\s*"
)


def split_question(question: str) -> list[str]:
  fragments = [fragment.strip() for fragment in SPLIT_PATTERN.split(question.strip())]
  return [fragment for fragment in fragments if fragment]
