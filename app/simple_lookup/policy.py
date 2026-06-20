"""H1 단순조회 입력값을 검증하고 조회 조건으로 정규화하는 Policy.

Policy 계층은 DB를 조회하지 않는다. 상위 에이전트가 만든
`SimpleLookupSlots`를 받아 다음 두 가지 값으로 정리하는 역할만 한다.

* criteria: DAO가 실제 조회에 사용할 조건
* ignored_slots: 현재 query_type에서는 사용하지 않는 정상 입력값

잘못된 요청은 `SimpleLookupPolicyError`로 알린다. 서비스 계층은 이 오류를
잡아 `SimpleLookupResult(success=False, ...)`로 변환하면 된다.
"""

from __future__ import annotations

import calendar
import math
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

from app.simple_lookup.dto import SimpleLookupQueryType, SimpleLookupSlots


# 설계 문서에 정의된 H1 정책값을 한곳에 모아 둔다. 숫자를 함수 내부에
# 직접 반복해서 쓰지 않으면 정책 변경 시 수정 위치가 명확해진다.
DEFAULT_TRADE_HISTORY_LIMIT = 5
MAX_TRADE_HISTORY_LIMIT = 20
SINGLE_AREA_TOLERANCE_SQM = 1.0
PYEONG_TO_SQM = 3.3058
ASSUMED_EXCLUSIVE_RATE = 0.75
MAX_PYEONG_AREA_DIFFERENCE_SQM = 3.0

# 상대 기간은 고정 목록이 아니라 "양의 정수 + m/y" 형식으로 받는다.
# 예: 2m(2개월), 8m(8개월), 2y(2년)
#
# 현재 실거래 데이터 보유 범위가 약 15년이므로 지나치게 큰 요청을 막기
# 위해 월은 최대 180개월, 연도는 최대 15년까지만 허용한다.
PERIOD_PATTERN = re.compile(r"^(?P<amount>[1-9]\d*)(?P<unit>[my])$")
MAX_PERIOD_MONTHS = 180
MAX_PERIOD_YEARS = 15

# location에서 사용하지 않는 슬롯이다. 값이 유효하면 무시하되 결과의
# ignored_slots에 남겨 상위 계층과 테스트에서 확인할 수 있게 한다.
LOCATION_UNUSED_SLOTS = (
  "area",
  "area_min",
  "area_max",
  "pyeong",
  "pyeong_min",
  "pyeong_max",
  "period",
  "start_date",
  "end_date",
  "limit",
)


class SimpleLookupPolicyError(ValueError):
  """사용자 입력 정책 위반을 표현하는 업무상 오류.

  `reason`은 H1 공통 실패 코드이며, `message`는 상위 계층이 로그나 응답에
  사용할 설명이다.
  """

  def __init__(
    self,
    reason: str,
    message: str,
  ) -> None:
    super().__init__(message)
    self.reason = reason
    self.message = message


@dataclass(slots=True)
class NormalizedLookupPolicy:
  """Policy 정규화 결과.

  아직 단지가 DB의 `complex_id`로 확정되기 전이므로 criteria에는 우선
  정규화된 `complex_name`을 담는다. 서비스 계층이 단지를 확정한 뒤
  `complex_id`를 추가하거나 단지명 조건을 교체할 수 있다.
  """

  criteria: dict[str, Any] = field(default_factory=dict)
  ignored_slots: dict[str, Any] = field(default_factory=dict)


def normalize_simple_lookup_policy(
  slots: SimpleLookupSlots,
  *,
  base_date: date | str | None = None,
) -> NormalizedLookupPolicy:
  """H1 입력 슬롯 전체를 query_type에 맞는 조회 조건으로 정규화한다.

  `base_date`는 기간 조건이 있을 때만 필요하다. 실제 서비스에서는 전체
  실거래 데이터의 최신 거래일을 DAO에서 조회해 전달하고, 단위 테스트에서는
  고정 날짜를 직접 넣어 재현 가능한 결과를 만든다.
  """

  complex_name = _normalize_complex_name(slots.complex_name)

  # location에서 사용하지 않는 값이라도 음수·NaN처럼 값 자체가 잘못되면
  # 조용히 버리지 않도록 먼저 모든 숫자 슬롯의 기본 유효성을 검사한다.
  _validate_all_numeric_slots(slots)

  if slots.query_type == SimpleLookupQueryType.LOCATION:
    # 위치 조회에서는 아래 슬롯을 실제 조회에 사용하지 않지만, 잘못된
    # 형식이나 모순된 값까지 조용히 무시하지는 않는다. base_date가 필요한
    # 미래 날짜 판정은 하지 않고 입력 자체의 형식과 관계만 확인한다.
    _validate_location_unused_slots(slots)
    return NormalizedLookupPolicy(
      criteria={"complex_name": complex_name},
      ignored_slots=_collect_present_slots(slots, LOCATION_UNUSED_SLOTS),
    )

  criteria: dict[str, Any] = {"complex_name": complex_name}
  criteria.update(normalize_area_policy(slots))
  ignored_slots: dict[str, Any] = {}

  # 명시 시작일과 종료일이 모두 있으면 그 범위가 사용자의 가장 구체적인
  # 요청이므로 period보다 우선한다. period를 조용히 버리지 않고 결과의
  # ignored_slots에 기록한다.
  period_slots = slots
  if slots.start_date is not None and slots.end_date is not None and slots.period is not None:
    ignored_slots["period"] = slots.period
    period_slots = slots.model_copy(update={"period": None})

  criteria.update(normalize_period_policy(period_slots, base_date=base_date))

  if slots.query_type == SimpleLookupQueryType.TRADE_HISTORY:
    criteria["limit"] = normalize_trade_history_limit(slots.limit)
  else:
    # location은 위에서 이미 반환됐고 query_type은 Enum으로 제한되므로
    # 여기까지 왔다면 남은 유형은 record_high뿐이다.
    normalize_record_high_limit(slots.limit)
    criteria["price_basis"] = "nominal_deal_amount"

  return NormalizedLookupPolicy(criteria=criteria, ignored_slots=ignored_slots)


def normalize_trade_history_limit(limit: int | None) -> int:
  """실거래 내역 조회 개수를 1~20 범위로 정규화한다."""

  if limit is None:
    return DEFAULT_TRADE_HISTORY_LIMIT
  if limit <= 0:
    raise SimpleLookupPolicyError(
      "invalid_request",
      "조회 개수는 1 이상이어야 합니다.",
    )
  return min(limit, MAX_TRADE_HISTORY_LIMIT)


def normalize_record_high_limit(limit: int | None) -> None:
  """최고가 조회가 한 건만 반환한다는 정책을 검증한다."""

  if limit is None or limit == 1:
    return
  if limit <= 0:
    raise SimpleLookupPolicyError(
      "invalid_request",
      "조회 개수는 1 이상이어야 합니다.",
    )
  raise SimpleLookupPolicyError(
    "unsupported_request",
    "최고가 조회는 한 건만 지원합니다.",
  )


def normalize_area_policy(slots: SimpleLookupSlots) -> dict[str, Any]:
  """㎡ 또는 평형 입력을 DAO가 사용할 면적 조건으로 정규화한다.

  단일 평형은 단지별 실제 면적 목록이 있어야 최종 면적을 확정할 수 있다.
  따라서 이 단계에서는 예상 전용면적만 계산하고, 실제 면적 선택은
  `resolve_nearest_actual_area`에서 수행한다.
  """

  has_area = slots.area is not None
  has_area_range = slots.area_min is not None or slots.area_max is not None
  has_pyeong = slots.pyeong is not None
  has_pyeong_range = slots.pyeong_min is not None or slots.pyeong_max is not None

  if has_area and has_area_range:
    raise SimpleLookupPolicyError(
      "invalid_request",
      "단일 전용면적과 전용면적 범위를 함께 사용할 수 없습니다.",
    )
  if has_pyeong and has_pyeong_range:
    raise SimpleLookupPolicyError(
      "invalid_request",
      "단일 평형과 평형 범위를 함께 사용할 수 없습니다.",
    )
  if (has_area or has_area_range) and (has_pyeong or has_pyeong_range):
    raise SimpleLookupPolicyError(
      "invalid_request",
      "전용면적 조건과 평형 조건을 함께 사용할 수 없습니다.",
    )

  if has_area:
    assert slots.area is not None
    return {
      "requested_area": slots.area,
      "area_min": slots.area - SINGLE_AREA_TOLERANCE_SQM,
      "area_max": slots.area + SINGLE_AREA_TOLERANCE_SQM,
      "area_match_policy": "plus_minus_1_sqm",
    }

  if has_area_range:
    if (
      slots.area_min is not None
      and slots.area_max is not None
      and slots.area_min > slots.area_max
    ):
      raise SimpleLookupPolicyError(
        "invalid_request",
        "전용면적 최솟값은 최댓값보다 클 수 없습니다.",
      )
    return {
      "area_min": slots.area_min,
      "area_max": slots.area_max,
      "area_match_policy": "explicit_area_range",
    }

  if has_pyeong:
    assert slots.pyeong is not None
    return {
      "requested_pyeong": slots.pyeong,
      "estimated_exclusive_area": estimate_exclusive_area(slots.pyeong),
      "exclusive_rate": ASSUMED_EXCLUSIVE_RATE,
      "area_match_policy": "nearest_actual_exclusive_area",
    }

  if has_pyeong_range:
    if slots.pyeong_min is None or slots.pyeong_max is None:
      raise SimpleLookupPolicyError(
        "invalid_request",
        "평형 범위는 최솟값과 최댓값을 모두 입력해야 합니다.",
      )
    if slots.pyeong_min > slots.pyeong_max:
      raise SimpleLookupPolicyError(
        "invalid_request",
        "평형 최솟값은 최댓값보다 클 수 없습니다.",
      )
    return {
      "requested_pyeong_min": slots.pyeong_min,
      "requested_pyeong_max": slots.pyeong_max,
      "area_min": estimate_exclusive_area(slots.pyeong_min),
      "area_max": estimate_exclusive_area(slots.pyeong_max),
      "exclusive_rate": ASSUMED_EXCLUSIVE_RATE,
      "area_match_policy": "estimated_pyeong_range",
    }

  return {}


def estimate_exclusive_area(pyeong: float) -> float:
  """공급면적 평형을 교육용 75% 전용률 기준 예상 전용면적으로 바꾼다."""

  return pyeong * PYEONG_TO_SQM * ASSUMED_EXCLUSIVE_RATE


def resolve_nearest_actual_area(
  estimated_area: float,
  actual_areas: Iterable[float],
) -> dict[str, Any]:
  """예상 전용면적과 가장 가까운 단지의 실제 전용면적을 확정한다.

  이 함수 자체는 DB를 모르며 DAO가 조회한 DISTINCT 전용면적 목록만 받는다.
  결과가 없으면 `no_result`, 3㎡보다 멀면 `unsupported_request`를 발생시킨다.

  예상 면적과의 차이가 같은 후보가 생기면 작은 전용면적을 선택한다.
  교육용 프로젝트에서 매우 드문 동률 상황을 별도 재질문 흐름으로
  확장하지 않고, 항상 같은 결과가 나오도록 단순한 우선순위를 사용한다.
  """

  _validate_positive_finite_number("estimated_area", estimated_area)

  normalized_areas: list[float] = []
  for actual_area in actual_areas:
    _validate_positive_finite_number("actual_area", actual_area)
    normalized_areas.append(float(actual_area))

  if not normalized_areas:
    raise SimpleLookupPolicyError(
      "no_result",
      "해당 단지에서 평형을 확인할 수 있는 거래 면적이 없습니다.",
    )

  # 정렬 기준의 첫 번째 값은 예상 면적과의 차이, 두 번째 값은 실제
  # 전용면적이다. 따라서 차이가 같으면 더 작은 전용면적이 선택된다.
  selected_area = min(
    normalized_areas,
    key=lambda actual_area: (abs(actual_area - estimated_area), actual_area),
  )
  difference = abs(selected_area - estimated_area)

  if difference > MAX_PYEONG_AREA_DIFFERENCE_SQM:
    raise SimpleLookupPolicyError(
      "unsupported_request",
      "입력 평형과 가까운 실제 전용면적을 찾지 못했습니다.",
    )

  return {
    "selected_exclusive_area": selected_area,
    "selected_area_difference": difference,
    # DAO는 부동소수점 등가 비교 대신 이 허용 오차를 사용한다.
    "selected_area_tolerance": 0.011,
  }


def normalize_period_policy(
  slots: SimpleLookupSlots,
  *,
  base_date: date | str | None,
) -> dict[str, Any]:
  """상대 기간과 명시 날짜를 최종 시작일·종료일로 정규화한다."""

  period = slots.period
  start_date = _parse_optional_date("start_date", slots.start_date)
  end_date = _parse_optional_date("end_date", slots.end_date)
  has_date_condition = period is not None or start_date is not None or end_date is not None

  if not has_date_condition:
    return {
      "period": None,
      "start_date": None,
      "end_date": None,
      "base_date": None,
      "date_scope": None,
    }

  normalized_base_date = _require_base_date(base_date)

  if period is not None:
    parse_period(period)
  if period is not None and start_date is not None:
    raise SimpleLookupPolicyError(
      "invalid_request",
      "period와 start_date를 함께 사용할 수 없습니다.",
    )

  # 시작일이 데이터 최신일보다 미래라면 조회 가능한 구간이 존재하지 않는다.
  if start_date is not None and start_date > normalized_base_date:
    raise SimpleLookupPolicyError(
      "invalid_request",
      "조회 시작일이 보유 데이터의 최신일보다 미래입니다.",
    )

  # 종료일만 미래인 경우에는 사용자의 시작 범위를 보존하면서 실제 보유
  # 데이터의 최신일까지로 제한한다.
  if end_date is not None and end_date > normalized_base_date:
    end_date = normalized_base_date

  # 명시 날짜 쌍이 있으면 period보다 우선한다. 현재 정책상 period와
  # start_date는 충돌하므로 이 분기는 순수 명시 날짜 요청에 해당한다.
  if start_date is not None and end_date is not None:
    if start_date > end_date:
      raise SimpleLookupPolicyError(
        "invalid_request",
        "조회 시작일은 종료일보다 늦을 수 없습니다.",
      )
    return {
      "period": None,
      "start_date": start_date.isoformat(),
      "end_date": end_date.isoformat(),
      "base_date": normalized_base_date.isoformat(),
      "date_scope": "explicit_range",
    }

  if period is not None:
    period_end = end_date or normalized_base_date
    period_start = subtract_calendar_period(period_end, period)
    return {
      "period": period,
      "start_date": period_start.isoformat(),
      "end_date": period_end.isoformat(),
      "base_date": normalized_base_date.isoformat(),
      "date_scope": "period_range",
    }

  if start_date is not None:
    return {
      "period": None,
      "start_date": start_date.isoformat(),
      "end_date": normalized_base_date.isoformat(),
      "base_date": normalized_base_date.isoformat(),
      "date_scope": "start_date_to_base_date",
    }

  assert end_date is not None
  return {
    "period": None,
    "start_date": None,
    "end_date": end_date.isoformat(),
    "base_date": normalized_base_date.isoformat(),
    "date_scope": "data_start_to_end_date",
  }


def subtract_calendar_period(value: date, period: str) -> date:
  """월말과 윤년을 보정하며 달력 월·연 단위로 기간을 역산한다."""

  unit, amount = parse_period(period)
  months_to_subtract = amount if unit == "month" else amount * 12
  total_months = value.year * 12 + (value.month - 1) - months_to_subtract
  target_year, zero_based_month = divmod(total_months, 12)
  target_month = zero_based_month + 1
  target_last_day = calendar.monthrange(target_year, target_month)[1]
  target_day = min(value.day, target_last_day)
  return date(target_year, target_month, target_day)


def parse_period(period: str) -> tuple[str, int]:
  """`2m`, `3y` 같은 상대 기간을 달력 단위와 숫자로 변환한다.

  상위 에이전트는 "최근 두 달", "지난 2년" 같은 자연어를 각각 `2m`,
  `2y` 형태로 표준화해서 전달한다. Policy는 자연어를 다시 해석하지 않고
  이 표준형의 형식과 허용 범위만 검증한다.
  """

  matched = PERIOD_PATTERN.fullmatch(period)
  if matched is None:
    raise SimpleLookupPolicyError(
      "invalid_request",
      "period는 양의 정수 뒤에 m(개월) 또는 y(년)를 붙여 입력해야 합니다.",
    )

  amount = int(matched.group("amount"))
  unit_code = matched.group("unit")

  if unit_code == "m":
    if amount > MAX_PERIOD_MONTHS:
      raise SimpleLookupPolicyError(
        "unsupported_request",
        f"개월 기간은 최대 {MAX_PERIOD_MONTHS}개월까지 지원합니다.",
      )
    return "month", amount

  if amount > MAX_PERIOD_YEARS:
    raise SimpleLookupPolicyError(
      "unsupported_request",
      f"연도 기간은 최대 {MAX_PERIOD_YEARS}년까지 지원합니다.",
    )
  return "year", amount


def _normalize_complex_name(complex_name: str | None) -> str:
  """단지명의 앞뒤·연속 공백을 정리하고 필수값을 검증한다."""

  if complex_name is None:
    raise SimpleLookupPolicyError(
      "invalid_request",
      "아파트 단지명이 필요합니다.",
    )
  normalized = " ".join(complex_name.split())
  if not normalized:
    raise SimpleLookupPolicyError(
      "invalid_request",
      "아파트 단지명이 필요합니다.",
    )
  return normalized


def _validate_all_numeric_slots(slots: SimpleLookupSlots) -> None:
  """모든 숫자 슬롯의 양수·유한값 여부를 query_type보다 먼저 검사한다."""

  for field_name in (
    "area",
    "area_min",
    "area_max",
    "pyeong",
    "pyeong_min",
    "pyeong_max",
  ):
    value = getattr(slots, field_name)
    if value is not None:
      _validate_positive_finite_number(field_name, value)

  # boolean은 DTO의 before validator에서 숫자로 변환되기 전에 차단한다.


def _validate_location_unused_slots(slots: SimpleLookupSlots) -> None:
  """location에서 무시할 기간·limit 슬롯의 기본 유효성을 검사한다.

  위치 조회에는 base_date가 필요하지 않으므로 미래 날짜 여부는 판단하지
  않는다. 다만 잘못된 날짜 형식, 지원하지 않는 period, 역전 날짜,
  period와 start_date 충돌, 0 이하 limit은 호출 오류로 처리한다.
  """

  if slots.period is not None:
    parse_period(slots.period)

  start_date = _parse_optional_date("start_date", slots.start_date)
  end_date = _parse_optional_date("end_date", slots.end_date)

  if slots.period is not None and start_date is not None:
    raise SimpleLookupPolicyError(
      "invalid_request",
      "period와 start_date를 함께 사용할 수 없습니다.",
    )
  if start_date is not None and end_date is not None and start_date > end_date:
    raise SimpleLookupPolicyError(
      "invalid_request",
      "조회 시작일은 종료일보다 늦을 수 없습니다.",
    )
  if slots.limit is not None and slots.limit <= 0:
    raise SimpleLookupPolicyError(
      "invalid_request",
      "조회 개수는 1 이상이어야 합니다.",
    )


def _validate_positive_finite_number(field_name: str, value: float) -> None:
  """면적·평형 값이 0보다 큰 유한 숫자인지 검사한다."""

  if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
    raise SimpleLookupPolicyError(
      "invalid_request",
      f"{field_name}은 0보다 큰 유한 숫자여야 합니다.",
    )


def _parse_optional_date(field_name: str, value: str | None) -> date | None:
  """선택 날짜 문자열을 ISO 날짜로 변환하고 형식 오류를 업무 실패로 바꾼다."""

  if value is None:
    return None
  try:
    return date.fromisoformat(value)
  except (TypeError, ValueError) as error:
    raise SimpleLookupPolicyError(
      "invalid_request",
      f"{field_name}은 YYYY-MM-DD 형식이어야 합니다.",
    ) from error


def _require_base_date(value: date | str | None) -> date:
  """기간 정규화에 필요한 데이터 기준일을 확인한다.

  base_date 누락은 사용자 슬롯 오류가 아니라 서비스 조립 단계의 오류이므로
  `SimpleLookupPolicyError`가 아닌 일반 `ValueError`로 알린다.
  """

  if value is None:
    raise ValueError("날짜 조건을 정규화하려면 base_date가 필요합니다.")
  if isinstance(value, date):
    return value
  try:
    return date.fromisoformat(value)
  except (TypeError, ValueError) as error:
    raise ValueError("base_date는 date 또는 YYYY-MM-DD 문자열이어야 합니다.") from error


def _collect_present_slots(
  slots: SimpleLookupSlots,
  field_names: Iterable[str],
) -> dict[str, Any]:
  """입력된 값만 골라 ignored_slots 사전으로 만든다."""

  return {
    field_name: getattr(slots, field_name)
    for field_name in field_names
    if getattr(slots, field_name) is not None
  }
