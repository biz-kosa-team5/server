from __future__ import annotations

from app.chatbot.dto import FragmentStatus, Intent
from app.chatbot.features.comparison.service import run_comparison
from app.chatbot.features.comparison.slots import extract_compare_slots
from app.chatbot.features.legal_contract.service import run_legal_contract
from app.chatbot.features.legal_contract.slots import extract_legal_contract_slots
from app.chatbot.features.price_trend.service import run_price_trend
from app.chatbot.features.price_trend.slots import extract_price_trend_slots
from app.chatbot.features.recommendation.service import run_recommendation
from app.chatbot.features.recommendation.slots import extract_recommendation_slots
from app.chatbot.features.simple_lookup.service import run_simple_lookup
from app.chatbot.features.simple_lookup.slots import extract_simple_lookup_slots
from app.chatbot.features.unsupported.service import run_unsupported
from app.chatbot.features.unsupported.slots import extract_unsupported_slots

from .handler import FeatureSpec


FEATURE_REGISTRY: dict[Intent, FeatureSpec] = {
  Intent.SIMPLE_LOOKUP: FeatureSpec(
    Intent.SIMPLE_LOOKUP,
    extract_simple_lookup_slots,
    run_simple_lookup,
    FragmentStatus.HANDLED,
  ),
  Intent.RECOMMENDATION: FeatureSpec(
    Intent.RECOMMENDATION,
    extract_recommendation_slots,
    run_recommendation,
    FragmentStatus.HANDLED,
  ),
  Intent.COMPARISON: FeatureSpec(
    Intent.COMPARISON,
    extract_compare_slots,
    run_comparison,
    FragmentStatus.HANDLED,
  ),
  Intent.PRICE_TREND: FeatureSpec(
    Intent.PRICE_TREND,
    extract_price_trend_slots,
    run_price_trend,
    FragmentStatus.HANDLED,
  ),
  Intent.LEGAL_CONTRACT: FeatureSpec(
    Intent.LEGAL_CONTRACT,
    extract_legal_contract_slots,
    run_legal_contract,
    FragmentStatus.HANDLED,
  ),
  Intent.UNSUPPORTED: FeatureSpec(
    Intent.UNSUPPORTED,
    extract_unsupported_slots,
    run_unsupported,
    FragmentStatus.UNSUPPORTED,
  ),
}


def get_feature_spec(intent: Intent) -> FeatureSpec:
  return FEATURE_REGISTRY[intent]
