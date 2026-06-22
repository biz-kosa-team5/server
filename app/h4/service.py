"""H4의 대상 확정과 전체 처리 흐름을 담당하는 Service.

현재는 단지·지역 시계열 조회를 다음 순서로 연결한다.

1. 날짜 계산에 사용할 base_date 준비
2. Policy로 슬롯 검증 및 조회 조건 정규화
3. 단지 또는 지역 Entity 확정
4. 단일 평형이면 단지의 실제 전용면적 확정
5. DAO의 시계열 집계 실행
6. 집계 행을 TrendPoint로 변환
7. TrendResult 반환

네 가지 H4 조회 유형을 모두 처리한다.

대상 확정의 기본 순서는 다음과 같다.

1. 정확히 일치하는 후보 검색
2. 정확 일치가 없으면 부분 일치 후보 검색
3. 후보 1개면 Entity 확정
4. 후보 0개면 target_not_found
5. 후보 여러 개면 ambiguous_target와 후보 목록 반환
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.h4.dao import PriceTrendDao
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
  normalize_trend_policy,
  resolve_nearest_actual_area,
)
from app.models import Complex, Region


class TrendTargetError(ValueError):
  """단지나 지역을 하나의 대상으로 확정하지 못한 업무상 오류."""

  def __init__(
    self,
    reason: str,
    message: str,
    *,
    candidates: list[dict[str, Any]] | None = None,
  ) -> None:
    super().__init__(message)
    self.reason = reason
    self.message = message
    self.candidates = candidates or []


def resolve_complex_target(
  dao: PriceTrendDao,
  complex_name: str,
) -> Complex:
  """단지명을 정확 일치, 부분 일치 순서로 검색해 한 곳을 확정한다."""

  exact_candidates = dao.find_exact_complexes(complex_name)
  if len(exact_candidates) == 1:
    return exact_candidates[0]
  if len(exact_candidates) > 1:
    raise _ambiguous_complex_error(exact_candidates)

  partial_candidates = dao.find_partial_complexes(complex_name)
  if len(partial_candidates) == 1:
    return partial_candidates[0]
  if len(partial_candidates) > 1:
    raise _ambiguous_complex_error(partial_candidates)

  raise TrendTargetError(
    "target_not_found",
    "입력한 이름과 일치하는 아파트 단지를 찾지 못했습니다.",
  )


def resolve_region_target(
  dao: PriceTrendDao,
  region_name: str,
) -> Region:
  """지역명 하나를 정확 일치, 부분 일치 순서로 검색해 확정한다."""

  exact_candidates = dao.find_exact_regions(region_name)
  if len(exact_candidates) == 1:
    return exact_candidates[0]
  if len(exact_candidates) > 1:
    raise _ambiguous_region_error(exact_candidates)

  partial_candidates = dao.find_partial_regions(region_name)
  if len(partial_candidates) == 1:
    return partial_candidates[0]
  if len(partial_candidates) > 1:
    raise _ambiguous_region_error(partial_candidates)

  raise TrendTargetError(
    "target_not_found",
    f"입력한 이름과 일치하는 지역을 찾지 못했습니다: {region_name}",
  )


def resolve_region_targets(
  dao: PriceTrendDao,
  region_names: list[str],
) -> list[Region]:
  """복수 지역명을 각각 확정하고 중복된 지역 Entity를 제거한다.

  하나라도 찾지 못하거나 후보가 여러 개면 일부 지역만으로 조회하지 않고
  전체 요청을 실패 처리한다. 사용자가 요청한 범위와 실제 조회 범위가
  달라지는 일을 방지하기 위한 정책이다.
  """

  resolved_regions: list[Region] = []
  resolved_ids: set[int] = set()

  for region_name in region_names:
    region = resolve_region_target(dao, region_name)
    if region.id not in resolved_ids:
      resolved_regions.append(region)
      resolved_ids.add(region.id)

  return resolved_regions


def resolve_region_scope_ids(
  regions: list[Region],
) -> list[int]:
  """확정된 지역 Entity를 실제 조회에 사용할 지역 ID로 변환한다.

  현재 공통 DB에서는 아파트 단지가 강남구·서초구·송파구와 같은 구 단위
  Region에 직접 연결된다. 따라서 하위 지역을 다시 검색할 필요 없이 확정한
  지역 ID를 그대로 ``Complex.region_id`` 조건에 사용한다.
  """

  return [region.id for region in regions]


class TrendService:
  """H4의 네 가지 query_type을 처리하는 애플리케이션 서비스.

  ``complex_trend``, ``region_trend``, ``price_ranking``,
  ``price_change_ranking``을 처리한다.
  생성자에 base_date를 전달하면 모든 상대 기간 계산에서 재사용한다.
  전달하지 않으면 필요한 요청에 한해 DB의 최신 거래일을 조회한다.
  """

  def __init__(
    self,
    dao: PriceTrendDao,
    *,
    base_date: date | str | None = None,
  ) -> None:
    self.dao = dao
    self.base_date = base_date

  def handle(self, slots: TrendSlots) -> TrendResult:
    """상위 에이전트가 전달한 슬롯을 처리해 H4 공통 결과를 반환한다."""

    # 오류가 대상 확정 이후 발생하더라도 실제 적용된 조건을 실패 결과에
    # 남길 수 있도록 Policy 결과를 try 바깥에 보관한다.
    policy: NormalizedTrendPolicy | None = None

    try:
      policy = self._normalize_policy(slots)

      if slots.query_type == TrendQueryType.COMPLEX_TREND:
        return self._handle_complex_trend(slots, policy)

      if slots.query_type == TrendQueryType.REGION_TREND:
        return self._handle_region_trend(slots, policy)

      if slots.query_type == TrendQueryType.PRICE_RANKING:
        return self._handle_price_ranking(slots, policy)

      # Enum으로 제한되어 있으므로 남은 유형은 price_change_ranking이다.
      return self._handle_price_change_ranking(slots, policy)

    except TrendPolicyError as error:
      return self._failure(
        slots,
        error.reason,
        error.message,
        criteria=policy.criteria if policy is not None else None,
        ignored_slots=policy.ignored_slots if policy is not None else None,
      )
    except TrendTargetError as error:
      return self._failure(
        slots,
        error.reason,
        error.message,
        criteria=policy.criteria if policy is not None else None,
        candidates=error.candidates,
        ignored_slots=policy.ignored_slots if policy is not None else None,
      )

  def _normalize_policy(self, slots: TrendSlots) -> NormalizedTrendPolicy:
    """필요할 때만 데이터 기준일을 준비한 뒤 Policy를 실행한다."""

    base_date = self.base_date

    # price_ranking은 기간을 전혀 입력하지 않으면 전체 데이터를 조회하므로
    # base_date가 필요 없다. 그 외 H4 조회는 기본 기간 또는 입력 기간을
    # 실제 날짜로 바꿔야 하므로 기준일이 필요하다.
    if _requires_base_date(slots) and base_date is None:
      base_date = self.dao.find_max_deal_date()
      if base_date is None:
        raise TrendPolicyError(
          "no_result",
          "기간 계산에 사용할 실거래 데이터가 없습니다.",
        )

    return normalize_trend_policy(slots, base_date=base_date)

  def _handle_complex_trend(
    self,
    slots: TrendSlots,
    policy: NormalizedTrendPolicy,
  ) -> TrendResult:
    """단지를 확정하고 해당 단지의 시계열 결과를 반환한다."""

    target = resolve_complex_target(
      self.dao,
      policy.criteria["complex_name"],
    )
    policy.criteria["complex_id"] = target.id
    policy.criteria["resolved_complex_name"] = target.name

    self._resolve_actual_area_if_needed(policy, target.id)

    rows = self.dao.find_complex_trend(target.id, policy.criteria)
    return self._trend_result(
      slots,
      policy,
      rows,
      success_message="단지 시세 추이를 조회했습니다.",
    )

  def _handle_region_trend(
    self,
    slots: TrendSlots,
    policy: NormalizedTrendPolicy,
  ) -> TrendResult:
    """단일 또는 복수 지역을 확정하고 통합 시계열을 반환한다."""

    region_ids = self._resolve_regions(policy)

    rows = self.dao.find_region_trend(region_ids, policy.criteria)
    return self._trend_result(
      slots,
      policy,
      rows,
      success_message="지역 시세 추이를 조회했습니다.",
    )

  def _handle_price_ranking(
    self,
    slots: TrendSlots,
    policy: NormalizedTrendPolicy,
  ) -> TrendResult:
    """지역을 확정하고 단지별 대표 실거래가 순위를 반환한다."""

    region_ids = self._resolve_regions(policy)
    rows = self.dao.find_price_ranking(region_ids, policy.criteria)

    if not rows:
      return self._failure(
        slots,
        "no_result",
        "조건에 맞는 실거래가 순위 데이터를 찾지 못했습니다.",
        criteria=policy.criteria,
        ignored_slots=policy.ignored_slots,
      )

    items = [PriceRankingItem(**row) for row in rows]
    return TrendResult(
      success=True,
      query_type=slots.query_type,
      data=items,
      criteria=policy.criteria,
      summary={
        "rank_order": policy.criteria["rank_order"],
        "result_count": len(items),
        "top_deal_amount": items[0].deal_amount,
        "deal_amount_unit": items[0].deal_amount_unit,
      },
      message="실거래가 순위를 조회했습니다.",
      ignored_slots=policy.ignored_slots,
    )

  def _handle_price_change_ranking(
    self,
    slots: TrendSlots,
    policy: NormalizedTrendPolicy,
  ) -> TrendResult:
    """지역을 확정하고 단지별 가격 변화율 순위를 반환한다."""

    region_ids = self._resolve_regions(policy)
    query_result = self.dao.find_price_change_ranking(
      region_ids,
      policy.criteria,
    )

    if query_result.eligible_count == 0:
      return self._failure(
        slots,
        "insufficient_data",
        "비교 구간의 최소 거래 건수를 충족하는 단지를 찾지 못했습니다.",
        criteria=policy.criteria,
        ignored_slots=policy.ignored_slots,
      )

    if not query_result.items:
      return self._failure(
        slots,
        "no_result",
        "비교 가능한 단지는 있지만 요청한 변화 방향에 해당하는 단지가 없습니다.",
        criteria=policy.criteria,
        ignored_slots=policy.ignored_slots,
      )

    items = [
      PriceChangeRankingItem(**row)
      for row in query_result.items
    ]
    return TrendResult(
      success=True,
      query_type=slots.query_type,
      data=items,
      criteria=policy.criteria,
      summary={
        "change_direction": policy.criteria["change_direction"],
        "result_count": len(items),
        "window_months": policy.criteria["window_months"],
        "min_trade_count": policy.criteria["min_trade_count"],
        "top_change_rate": items[0].change_rate,
      },
      message="가격 변화율 순위를 조회했습니다.",
      ignored_slots=policy.ignored_slots,
    )

  def _resolve_regions(
    self,
    policy: NormalizedTrendPolicy,
  ) -> list[int]:
    """Policy의 단일·복수 지역명을 DB 지역 ID 목록으로 확정한다."""

    if "region_name" in policy.criteria:
      regions = [
        resolve_region_target(
          self.dao,
          policy.criteria["region_name"],
        )
      ]
    else:
      regions = resolve_region_targets(
        self.dao,
        policy.criteria["region_names"],
      )

    region_ids = resolve_region_scope_ids(regions)
    policy.criteria["region_ids"] = region_ids
    policy.criteria["resolved_region_names"] = [
      region.name for region in regions
    ]
    return region_ids

  def _resolve_actual_area_if_needed(
    self,
    policy: NormalizedTrendPolicy,
    complex_id: int,
  ) -> None:
    """단일 평형을 해당 단지에서 실제 거래된 전용면적으로 연결한다."""

    if policy.criteria.get("area_match_policy") != "nearest_actual_exclusive_area":
      return

    estimated_area = float(policy.criteria["estimated_exclusive_area"])
    actual_areas = self.dao.find_distinct_areas(complex_id)
    policy.criteria.update(
      resolve_nearest_actual_area(
        estimated_area,
        actual_areas,
      )
    )

  def _trend_result(
    self,
    slots: TrendSlots,
    policy: NormalizedTrendPolicy,
    rows: list[dict[str, Any]],
    *,
    success_message: str,
  ) -> TrendResult:
    """DAO 집계 결과를 TrendPoint 목록과 시계열 요약으로 변환한다."""

    if not rows:
      return self._failure(
        slots,
        "no_result",
        "조건에 맞는 시세 추이 데이터를 찾지 못했습니다.",
        criteria=policy.criteria,
        ignored_slots=policy.ignored_slots,
      )

    points = [TrendPoint(**row) for row in rows]
    return TrendResult(
      success=True,
      query_type=slots.query_type,
      data=points,
      criteria=policy.criteria,
      summary=_build_trend_summary(points, policy.criteria["primary_metric"]),
      message=success_message,
      ignored_slots=policy.ignored_slots,
    )

  @staticmethod
  def _failure(
    slots: TrendSlots,
    reason: str,
    message: str,
    *,
    criteria: dict[str, Any] | None = None,
    candidates: list[dict[str, Any]] | None = None,
    ignored_slots: dict[str, Any] | None = None,
  ) -> TrendResult:
    """예상 가능한 업무상 실패를 H4 공통 결과 구조로 만든다."""

    return TrendResult(
      success=False,
      query_type=slots.query_type,
      data=[],
      criteria=criteria or {},
      reason=reason,
      message=message,
      candidates=candidates or [],
      ignored_slots=ignored_slots or {},
    )


def _requires_base_date(slots: TrendSlots) -> bool:
  """해당 요청의 기간 정규화에 데이터 기준일이 필요한지 판단한다."""

  if slots.query_type != TrendQueryType.PRICE_RANKING:
    return True
  return any((
    slots.period is not None,
    slots.start_date is not None,
    slots.end_date is not None,
  ))


def _build_trend_summary(
  points: list[TrendPoint],
  primary_metric: str,
) -> dict[str, Any]:
  """첫 관측값과 마지막 관측값으로 전체 변화량·변화율을 계산한다."""

  first_point = points[0]
  last_point = points[-1]
  first_value = float(getattr(first_point, primary_metric))
  last_value = float(getattr(last_point, primary_metric))
  change_amount = last_value - first_value
  change_rate = None if first_value == 0 else (change_amount / first_value) * 100

  return {
    "primary_metric": primary_metric,
    "first_period": first_point.period_start,
    "last_period": last_point.period_start,
    "first_value": round(first_value, 2),
    "last_value": round(last_value, 2),
    "change_amount": round(change_amount, 2),
    "change_rate": None if change_rate is None else round(change_rate, 2),
    "observed_period_count": len(points),
    "total_trade_count": sum(point.trade_count for point in points),
  }


def _ambiguous_complex_error(candidates: list[Complex]) -> TrendTargetError:
  """동명·유사 단지 Entity를 상위 에이전트용 후보 목록으로 변환한다."""

  return TrendTargetError(
    "ambiguous_target",
    "같은 이름 또는 유사한 이름의 아파트 단지가 여러 개 있습니다.",
    candidates=[
      {
        "target_type": "complex",
        "complex_id": row.id,
        "complex_name": row.name,
        "trade_name": row.trade_name,
        "address": row.address,
        "region_id": row.region_id,
      }
      for row in candidates
    ],
  )


def _ambiguous_region_error(candidates: list[Region]) -> TrendTargetError:
  """동명·유사 지역 Entity를 상위 에이전트용 후보 목록으로 변환한다."""

  return TrendTargetError(
    "ambiguous_target",
    "같은 이름 또는 유사한 이름의 지역이 여러 개 있습니다.",
    candidates=[
      {
        "target_type": "region",
        "region_id": row.id,
        "region_name": row.name,
        "region_code": row.code,
        "region_type": row.type,
        "parent_id": row.parent_id,
      }
      for row in candidates
    ],
  )
