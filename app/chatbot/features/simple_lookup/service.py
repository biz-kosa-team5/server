"""H1 단순조회 전체 흐름을 조립하는 Service.

Service는 지금까지 분리해 만든 계층을 다음 순서로 연결한다.

1. 날짜 조건에 필요한 base_date 준비
2. Policy로 슬롯 검증 및 조회 조건 정규화
3. Target으로 단지 한 곳 확정
4. 평형 입력이면 실제 거래 전용면적 확정
5. query_type에 맞는 DAO 조회
6. Entity를 출력 DTO로 변환
7. 모든 업무 결과를 SimpleLookupResult로 반환

DB 연결 실패나 SQL 실행 오류는 업무상 실패로 감추지 않는다. Service는
Policy와 Target에서 발생한 예상 가능한 업무 오류만 Result로 변환한다.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models import Complex, Trade
from app.chatbot.features.simple_lookup.dao import SimpleLookupDao
from app.chatbot.features.simple_lookup.dto import (
  LocationData,
  SimpleLookupQueryType,
  SimpleLookupResult,
  SimpleLookupSlots,
  TradeData,
)
from app.chatbot.features.simple_lookup.policy import (
  NormalizedLookupPolicy,
  SimpleLookupPolicyError,
  normalize_simple_lookup_policy,
  resolve_nearest_actual_area,
)


class SimpleLookupTargetError(ValueError):
  """단지를 한 곳으로 확정하지 못했을 때 발생하는 업무상 오류."""

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
  dao: SimpleLookupDao,
  complex_name: str,
) -> Complex:
  """단지명을 정확 일치, 부분 일치 순서로 검색해 한 곳을 확정한다."""

  exact_candidates = dao.find_exact_complexes(complex_name)
  if len(exact_candidates) == 1:
    return exact_candidates[0]
  if len(exact_candidates) > 1:
    raise _ambiguous_target_error(exact_candidates)

  partial_candidates = dao.find_partial_complexes(complex_name)
  if len(partial_candidates) == 1:
    return partial_candidates[0]
  if len(partial_candidates) > 1:
    raise _ambiguous_target_error(partial_candidates)

  raise SimpleLookupTargetError(
    "target_not_found",
    "입력한 이름과 일치하는 아파트 단지를 찾지 못했습니다.",
  )


def _ambiguous_target_error(candidates: list[Complex]) -> SimpleLookupTargetError:
  """복수 단지 Entity를 상위 에이전트가 사용할 후보 목록으로 바꾼다."""

  return SimpleLookupTargetError(
    "ambiguous_target",
    "같은 이름 또는 유사한 이름의 아파트 단지가 여러 개 있습니다.",
    candidates=[
      {
        "complex_id": row.id,
        "complex_name": row.name,
        "trade_name": row.trade_name,
        "address": row.address,
      }
      for row in candidates
    ],
  )


class SimpleLookupService:
  """H1의 세 가지 query_type을 처리하는 애플리케이션 서비스.

  `base_date`를 생성자에 전달하면 모든 날짜 요청에서 그 값을 재사용한다.
  발표나 운영 환경에서는 DB 적재가 끝난 뒤 확정한 최신 거래일을 주입하면
  요청마다 MAX(deal_date)를 조회하지 않아도 된다.

  `base_date`가 없을 때는 날짜 조건이 있는 요청에 한해서 DAO에서 최신일을
  조회한다. 날짜 조건이 없는 위치·전체 기간 조회에는 불필요한 조회를 하지
  않는다.
  """

  def __init__(
    self,
    dao: SimpleLookupDao,
    *,
    base_date: date | str | None = None,
  ) -> None:
    self.dao = dao
    self.base_date = base_date

  def handle(self, slots: SimpleLookupSlots) -> SimpleLookupResult:
    """상위 에이전트가 전달한 슬롯을 처리해 H1 공통 결과를 반환한다."""

    # 오류가 처리 도중 발생해도 그 시점까지 정규화된 조건을 실패 결과에
    # 남길 수 있도록 Policy 결과를 try 바깥에 보관한다.
    policy: NormalizedLookupPolicy | None = None

    try:
      policy = self._normalize_policy(slots)
      target = resolve_complex_target(
        self.dao,
        policy.criteria["complex_name"],
      )

      # 이후 조회와 결과 설명에 실제 확정된 DB 식별자를 사용하도록
      # Policy criteria를 보강한다. 입력 문자열은 디버깅을 위해 유지한다.
      policy.criteria["complex_id"] = target.id
      policy.criteria["resolved_complex_name"] = target.name

      if slots.query_type == SimpleLookupQueryType.LOCATION:
        return self._handle_location(slots, policy, target)

      self._resolve_actual_area_if_needed(policy, target.id)

      if slots.query_type == SimpleLookupQueryType.TRADE_HISTORY:
        return self._handle_trade_history(slots, policy, target.id)

      # location은 앞에서 반환됐고 query_type은 Enum으로 제한되므로
      # 남은 유형은 record_high뿐이다.
      return self._handle_record_high(slots, policy, target.id)

    except SimpleLookupPolicyError as error:
      return self._failure(
        slots,
        error.reason,
        error.message,
        criteria=policy.criteria if policy is not None else None,
        ignored_slots=policy.ignored_slots if policy is not None else None,
      )
    except SimpleLookupTargetError as error:
      return self._failure(
        slots,
        error.reason,
        error.message,
        criteria=policy.criteria if policy is not None else None,
        candidates=error.candidates,
        ignored_slots=policy.ignored_slots if policy is not None else None,
      )

  def _normalize_policy(self, slots: SimpleLookupSlots) -> NormalizedLookupPolicy:
    """날짜 조건이 있을 때만 base_date를 준비해 Policy를 실행한다."""

    base_date = self.base_date
    if (
      slots.query_type != SimpleLookupQueryType.LOCATION
      and _has_date_condition(slots)
      and base_date is None
    ):
      base_date = self.dao.find_max_deal_date()
      if base_date is None:
        raise SimpleLookupPolicyError(
          "no_result",
          "기간 계산에 사용할 실거래 데이터가 없습니다.",
        )

    return normalize_simple_lookup_policy(slots, base_date=base_date)

  def _resolve_actual_area_if_needed(
    self,
    policy: NormalizedLookupPolicy,
    complex_id: int,
  ) -> None:
    """단일 평형 요청을 해당 단지의 실제 거래 전용면적으로 연결한다.

    직접 ㎡를 입력했거나 평형대 범위를 입력한 경우에는 Policy가 이미
    area_min/area_max를 만들었으므로 별도 면적 조회가 필요하지 않다.
    """

    estimated_area = policy.criteria.get("estimated_exclusive_area")
    if estimated_area is None:
      return

    actual_areas = self.dao.find_distinct_areas(complex_id)
    policy.criteria.update(
      resolve_nearest_actual_area(
        float(estimated_area),
        actual_areas,
      )
    )

  def _handle_location(
    self,
    slots: SimpleLookupSlots,
    policy: NormalizedLookupPolicy,
    target: Complex,
  ) -> SimpleLookupResult:
    """확정된 Complex Entity를 위치 결과 DTO 한 건으로 변환한다."""

    # 주소와 좌표가 모두 없으면 위치 질문에 제공할 실제 정보가 없다.
    # 좌표만 없고 주소가 있으면 정상 결과로 반환한다.
    if target.address is None and target.latitude is None and target.longitude is None:
      return self._failure(
        slots,
        "no_result",
        "해당 아파트 단지의 위치 정보가 없습니다.",
        criteria=policy.criteria,
        ignored_slots=policy.ignored_slots,
      )

    return SimpleLookupResult(
      success=True,
      query_type=slots.query_type,
      data=[_to_location_data(target)],
      criteria=policy.criteria,
      message="아파트 위치를 조회했습니다.",
      ignored_slots=policy.ignored_slots,
    )

  def _handle_trade_history(
    self,
    slots: SimpleLookupSlots,
    policy: NormalizedLookupPolicy,
    complex_id: int,
  ) -> SimpleLookupResult:
    """조건에 맞는 실거래 내역을 최신순 목록으로 반환한다."""

    rows = self.dao.find_trade_history(complex_id, policy.criteria)
    if not rows:
      return self._failure(
        slots,
        "no_result",
        "조건에 맞는 실거래 내역을 찾지 못했습니다.",
        criteria=policy.criteria,
        ignored_slots=policy.ignored_slots,
      )

    return SimpleLookupResult(
      success=True,
      query_type=slots.query_type,
      data=[_to_trade_data(row) for row in rows],
      criteria=policy.criteria,
      message="실거래 내역을 조회했습니다.",
      ignored_slots=policy.ignored_slots,
    )

  def _handle_record_high(
    self,
    slots: SimpleLookupSlots,
    policy: NormalizedLookupPolicy,
    complex_id: int,
  ) -> SimpleLookupResult:
    """조건 안에서 명목 거래금액이 가장 높은 거래 한 건을 반환한다."""

    row = self.dao.find_record_high(complex_id, policy.criteria)
    if row is None:
      return self._failure(
        slots,
        "no_result",
        "조건에 맞는 최고가 거래를 찾지 못했습니다.",
        criteria=policy.criteria,
        ignored_slots=policy.ignored_slots,
      )

    # H1의 data는 항상 리스트이므로 최고가 한 건도 리스트에 담는다.
    return SimpleLookupResult(
      success=True,
      query_type=slots.query_type,
      data=[_to_trade_data(row)],
      criteria=policy.criteria,
      message="최고가 거래를 조회했습니다.",
      ignored_slots=policy.ignored_slots,
    )

  @staticmethod
  def _failure(
    slots: SimpleLookupSlots,
    reason: str,
    message: str,
    *,
    criteria: dict[str, Any] | None = None,
    candidates: list[dict[str, Any]] | None = None,
    ignored_slots: dict[str, Any] | None = None,
  ) -> SimpleLookupResult:
    """업무상 실패를 H1 공통 반환 구조로 만든다."""

    return SimpleLookupResult(
      success=False,
      query_type=slots.query_type,
      data=[],
      criteria=criteria or {},
      reason=reason,
      message=message,
      candidates=candidates or [],
      ignored_slots=ignored_slots or {},
    )


def _has_date_condition(slots: SimpleLookupSlots) -> bool:
  """상대 기간이나 명시 날짜 중 하나라도 입력됐는지 확인한다."""

  return any((
    slots.period is not None,
    slots.start_date is not None,
    slots.end_date is not None,
  ))


def _to_location_data(row: Complex) -> LocationData:
  """Complex Entity를 외부 반환용 위치 DTO로 변환한다."""

  return LocationData(
    complex_id=row.id,
    complex_name=row.name,
    trade_name=row.trade_name,
    address=row.address,
    latitude=row.latitude,
    longitude=row.longitude,
  )


def _to_trade_data(row: Trade) -> TradeData:
  """Trade Entity를 외부 반환용 거래 DTO로 변환한다."""

  return TradeData(
    trade_id=row.id,
    deal_date=row.deal_date,
    deal_amount=row.deal_amount,
    exclusive_area=row.excl_area,
    floor=row.floor,
    apt_dong=row.apt_dong,
  )


def run_simple_lookup(session: Session, slots: dict[str, Any], _: str = "") -> dict[str, Any]:
  try:
    request = SimpleLookupSlots(**slots)
  except ValidationError as error:
    return {
      "handler": "simple_lookup",
      "success": False,
      "reason": "invalid_request",
      "message": "단순 조회 요청 슬롯이 올바르지 않습니다.",
      "errors": validation_errors(error),
      "criteria": {},
      "data": [],
    }

  result = SimpleLookupService(SimpleLookupDao(session)).handle(request).model_dump(mode="json")
  return {"handler": "simple_lookup", **result}


def validation_errors(error: ValidationError) -> list[dict[str, Any]]:
  return [
    {
      "loc": list(item["loc"]),
      "msg": item["msg"],
      "type": item["type"],
    }
    for item in error.errors()
  ]
