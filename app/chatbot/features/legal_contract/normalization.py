from __future__ import annotations

import re
import unicodedata


_PUNCTUATION = str.maketrans({
  character: " "
  for character in ".,!?;:()[]{}\"'`~、。·…“”‘’"
})


def normalize_query(question: str) -> str:
  normalized = unicodedata.normalize("NFC", question)
  normalized = normalized.translate(_PUNCTUATION)
  normalized = normalized.lower()
  return re.sub(r"\s+", " ", normalized).strip()
