from __future__ import annotations

from ..types import Intent
from .base import IntentHandler
from ..features.comparison import ComparisonHandler
from ..features.legal_contract import LegalContractHandler
from ..features.price_trend import PriceTrendHandler
from ..features.recommendation import RecommendationHandler
from ..features.simple_lookup import SimpleLookupHandler
from ..features.unsupported import UnsupportedHandler


HANDLER_REGISTRY: dict[Intent, IntentHandler] = {
  Intent.RECOMMENDATION: RecommendationHandler(),
  Intent.COMPARISON: ComparisonHandler(),
  Intent.LEGAL_CONTRACT: LegalContractHandler(),
  Intent.SIMPLE_LOOKUP: SimpleLookupHandler(),
  Intent.PRICE_TREND: PriceTrendHandler(),
  Intent.UNSUPPORTED: UnsupportedHandler(),
}


def get_handler(intent: Intent) -> IntentHandler:
  return HANDLER_REGISTRY[intent]
