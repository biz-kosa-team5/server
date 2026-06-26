"""H4 price_trend feature exports."""

from .dao import PriceTrendDao
from .dto import (
    ANALYSIS_RANKING,
    ANALYSIS_TIMESERIES,
    RANK_BY_CHANGE_RATE,
    RANK_BY_MAX_DEAL_AMOUNT,
    RANK_BY_MIN_DEAL_AMOUNT,
    TARGET_COMPLEX,
    TARGET_REGION,
    PriceChangeRankingItem,
    TrendAnalysisSpec,
    TrendError,
    TrendPoint,
    TrendResult,
    TrendSlots,
)
from .policy import (
    BASE_DATE,
    build_change_windows,
    normalize_interval,
    normalize_trend_policy,
    parse_period,
)
from .service import TrendService, run_price_trend
from .slots import extract_price_trend_slots

__all__ = [
    "BASE_DATE",
    "ANALYSIS_RANKING",
    "ANALYSIS_TIMESERIES",
    "RANK_BY_CHANGE_RATE",
    "RANK_BY_MAX_DEAL_AMOUNT",
    "RANK_BY_MIN_DEAL_AMOUNT",
    "TARGET_COMPLEX",
    "TARGET_REGION",
    "PriceChangeRankingItem",
    "PriceTrendDao",
    "TrendAnalysisSpec",
    "TrendError",
    "TrendPoint",
    "TrendResult",
    "TrendService",
    "TrendSlots",
    "build_change_windows",
    "extract_price_trend_slots",
    "normalize_interval",
    "normalize_trend_policy",
    "parse_period",
    "run_price_trend",
]
