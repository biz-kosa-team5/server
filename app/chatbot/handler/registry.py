from __future__ import annotations

from ..dto.chatbot_dto import Intent
from .base import IntentHandler
from .comparison_handler import ComparisonHandler
from .legal_contract_handler import LegalContractHandler
from .not_implemented_handler import NotImplementedHandler
from .recommendation_handler import RecommendationHandler
from .unsupported_handler import UnsupportedHandler


HANDLER_REGISTRY: dict[Intent, IntentHandler] = {
  Intent.RECOMMENDATION: RecommendationHandler(),
  Intent.COMPARISON: ComparisonHandler(),
  Intent.LEGAL_CONTRACT: LegalContractHandler(),
  Intent.SIMPLE_LOOKUP: NotImplementedHandler(),
  Intent.PRICE_TREND: NotImplementedHandler(),
  Intent.UNSUPPORTED: UnsupportedHandler(),
}


def get_handler(intent: Intent) -> IntentHandler:
  return HANDLER_REGISTRY[intent]
