from __future__ import annotations

from typing import Any

from .normalization import normalize_query


def extract_legal_contract_slots(question: str) -> dict[str, Any]:
  return {
    "original_query": question,
    "normalized_query": normalize_query(question),
    "expanded_terms": [],
  }
