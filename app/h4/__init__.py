"""H4 시세추이·시계열 조회 핸들러 패키지.

DTO, Policy, DAO, 대상 확정 기능과 네 가지 H4 조회 Service를 외부에
공개한다.
"""

from app.h4.dao import PriceChangeRankingQueryResult, PriceTrendDao
from app.h4.dto import (
  PriceChangeRankingItem,
  PriceRankingItem,
  TrendPoint,
  TrendQueryType,
  TrendResult,
  TrendSlots,
)
from app.h4.policy import (
  NormalizedTrendPolicy,
  TrendPolicyError,
  build_change_windows,
  estimate_exclusive_area,
  normalize_trend_policy,
  parse_period,
  resolve_nearest_actual_area,
)
from app.h4.service import (
  TrendService,
  TrendTargetError,
  resolve_complex_target,
  resolve_region_scope_ids,
  resolve_region_target,
  resolve_region_targets,
)

__all__ = [
  "NormalizedTrendPolicy",
  "PriceChangeRankingQueryResult",
  "PriceTrendDao",
  "PriceChangeRankingItem",
  "PriceRankingItem",
  "TrendPoint",
  "TrendPolicyError",
  "TrendQueryType",
  "TrendResult",
  "TrendService",
  "TrendSlots",
  "TrendTargetError",
  "build_change_windows",
  "estimate_exclusive_area",
  "normalize_trend_policy",
  "parse_period",
  "resolve_complex_target",
  "resolve_nearest_actual_area",
  "resolve_region_scope_ids",
  "resolve_region_target",
  "resolve_region_targets",
]
