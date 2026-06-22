from __future__ import annotations

from enum import StrEnum


class Intent(StrEnum):
  SIMPLE_LOOKUP = "simple_lookup"
  RECOMMENDATION = "recommendation"
  COMPARISON = "comparison"
  PRICE_TREND = "price_trend"
  LEGAL_CONTRACT = "legal_contract"
  UNSUPPORTED = "unsupported"


class FragmentStatus(StrEnum):
  HANDLED = "handled"
  NOT_IMPLEMENTED = "not_implemented"
  UNSUPPORTED = "unsupported"
