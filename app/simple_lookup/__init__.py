"""H1 단순조회 기능 패키지.

이 패키지는 특정 아파트 단지 한 곳의 위치, 최근 거래, 최고가 거래를
조회하는 H1 핸들러를 담는다.

입력/출력 DTO, 정책 정규화, 공통 DB 조회, 단지 후보 확정 기능을
외부에서 일관된 경로로 가져갈 수 있도록 공개한다.
"""

from app.simple_lookup.dao import SimpleLookupDao
from app.simple_lookup.dto import (
  LocationData,
  SimpleLookupQueryType,
  SimpleLookupResult,
  SimpleLookupSlots,
  TradeData,
)
from app.simple_lookup.policy import (
  NormalizedLookupPolicy,
  SimpleLookupPolicyError,
  estimate_exclusive_area,
  normalize_simple_lookup_policy,
  parse_period,
  resolve_nearest_actual_area,
)
from app.simple_lookup.service import (
  SimpleLookupService,
  SimpleLookupTargetError,
  resolve_complex_target,
)

__all__ = [
  "LocationData",
  "NormalizedLookupPolicy",
  "SimpleLookupDao",
  "SimpleLookupPolicyError",
  "SimpleLookupQueryType",
  "SimpleLookupResult",
  "SimpleLookupService",
  "SimpleLookupSlots",
  "SimpleLookupTargetError",
  "TradeData",
  "estimate_exclusive_area",
  "normalize_simple_lookup_policy",
  "parse_period",
  "resolve_nearest_actual_area",
  "resolve_complex_target",
]
