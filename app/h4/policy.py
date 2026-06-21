"""H4 입력 슬롯을 검증하고 DAO가 사용할 조회 조건으로 정규화한다.

Policy는 DB를 직접 조회하지 않는다. 상위 에이전트가 만든 ``TrendSlots``를
받아 다음 두 가지 값으로 정리한다.

- criteria: DAO가 실제 조회에 사용할 조건
- ignored_slots: 현재 query_type에서는 사용하지 않는 정상 입력값

잘못된 요청은 ``TrendPolicyError``로 알린다. 이후 Service는 이 예외를
잡아 ``TrendResult(success=False, ...)`` 형태의 업무 실패로 변환한다.
"""

from __future__ import annotations

import calendar
import math
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Iterable

from app.h4.dto import TrendQueryType, TrendSlots


# 여러 함수에서 함께 사용하는 정책값을 한곳에 모아 둔다. 나중에 팀에서
# 기본 기간이나 최대 조회 개수를 바꾸더라도 이 부분만 수정하면 된다.
DEFAULT_TREND_PERIOD = "3y"
DEFAULT_CHANGE_RANKING_PERIOD = "1y"
DEFAULT_RANKING_LIMIT = 5
MAX_RANKING_LIMIT = 20
MIN_CHANGE_WINDOW_TRADE_COUNT = 2

SINGLE_AREA_TOLERANCE_SQM = 1.0
PYEONG_TO_SQM = 3.3058
ASSUMED_EXCLUSIVE_RATE = 0.75
MAX_PYEONG_AREA_DIFFERENCE_SQM = 3.0

PERIOD_PATTERN = re.compile(r"^(?P<amount>[1-9]\d*)(?P<unit>[my])$")
MAX_PERIOD_MONTHS = 180
MAX_PERIOD_YEARS = 15

ALLOWED_INTERVALS = {"month", "quarter", "year"}
ALLOWED_CHANGE_DIRECTIONS = {"up", "down", "absolute"}
ALLOWED_RANK_ORDERS = {"highest", "lowest"}


class TrendPolicyError(ValueError):
  """사용자 입력의 정책 위반을 표현하는 업무상 오류."""

  def __init__(self, reason: str, message: str) -> None:
    super().__init__(message)
    self.reason = reason
    self.message = message


@dataclass(slots=True)
class NormalizedTrendPolicy:
  """Policy 정규화 결과.

  이 단계에서는 단지명과 지역명을 DB ID로 바꾸지 않는다. 대상 확정
  단계에서 Complex 또는 Region을 찾은 뒤 Service가 ID 조건을 추가한다.
  """

  criteria: dict[str, Any] = field(default_factory=dict)
  ignored_slots: dict[str, Any] = field(default_factory=dict)


def normalize_trend_policy(
  slots: TrendSlots,
  *,
  base_date: date | str | None = None,
) -> NormalizedTrendPolicy:
  """H4 슬롯 전체를 query_type에 맞는 조회 조건으로 정규화한다."""

  _validate_all_numeric_slots(slots)
  target_criteria = normalize_target_policy(slots)
  area_criteria = normalize_area_policy(
    slots,
    use_actual_complex_area=slots.query_type == TrendQueryType.COMPLEX_TREND,
  )

  criteria: dict[str, Any] = {
    **target_criteria,
    **area_criteria,
  }
  ignored_slots: dict[str, Any] = {}

  # 명시 시작일과 종료일이 모두 있으면 가장 구체적인 날짜 범위로 본다.
  # period가 함께 전달되면 조용히 잃어버리지 않고 ignored_slots에 남긴다.
  period_slots = slots
  if slots.start_date is not None and slots.end_date is not None and slots.period is not None:
    ignored_slots["period"] = slots.period
    period_slots = slots.model_copy(update={"period": None})

  default_period = _default_period_for(slots.query_type)
  criteria.update(
    normalize_period_policy(
      period_slots,
      base_date=base_date,
      default_period=default_period,
    )
  )

  if slots.query_type in {
    TrendQueryType.COMPLEX_TREND,
    TrendQueryType.REGION_TREND,
  }:
    criteria["interval"] = normalize_interval(
      slots.interval,
      start_date=criteria["start_date"],
      end_date=criteria["end_date"],
    )
    criteria["primary_metric"] = (
      "avg_deal_amount" if _has_area_filter(criteria) else "avg_price_per_sqm"
    )
    ignored_slots.update(
      _collect_present_slots(slots, ("change_direction", "rank_order", "limit"))
    )

  elif slots.query_type == TrendQueryType.PRICE_CHANGE_RANKING:
    # interval은 변화율 순위 SQL에서 사용하지 않지만, 오타가 있는 값까지
    # 무시하지 않도록 허용값 검증 후 ignored_slots에 기록한다.
    _validate_optional_interval(slots.interval)
    ignored_slots.update(_collect_present_slots(slots, ("interval", "rank_order")))
    criteria["change_direction"] = normalize_change_direction(slots.change_direction)
    criteria["limit"] = normalize_ranking_limit(slots.limit)
    criteria["min_trade_count"] = MIN_CHANGE_WINDOW_TRADE_COUNT
    criteria.update(
      build_change_windows(
        criteria["start_date"],
        criteria["end_date"],
      )
    )

  else:
    # Enum으로 제한되어 있으므로 남은 유형은 price_ranking이다.
    _validate_optional_interval(slots.interval)
    ignored_slots.update(
      _collect_present_slots(slots, ("interval", "change_direction"))
    )
    criteria["rank_order"] = normalize_rank_order(slots.rank_order)
    criteria["limit"] = normalize_ranking_limit(slots.limit)

  return NormalizedTrendPolicy(
    criteria=criteria,
    ignored_slots=ignored_slots,
  )


def normalize_target_policy(slots: TrendSlots) -> dict[str, Any]:
  """query_type에 맞는 단지명 또는 지역명을 정리한다."""

  complex_name = _normalize_optional_name(slots.complex_name)
  region_name = _normalize_optional_name(slots.region_name)
  region_names = _normalize_region_names(slots.region_names)

  supplied_target_count = sum(
    value is not None
    for value in (complex_name, region_name, region_names)
  )
  if supplied_target_count > 1:
    raise TrendPolicyError(
      "invalid_request",
      "단지명, 단일 지역명, 복수 지역명은 함께 사용할 수 없습니다.",
    )

  if slots.query_type == TrendQueryType.COMPLEX_TREND:
    if complex_name is None:
      raise TrendPolicyError(
        "invalid_request",
        "단지 시세 추이 조회에는 아파트 단지명이 필요합니다.",
      )
    return {"complex_name": complex_name}

  if region_name is None and region_names is None:
    raise TrendPolicyError(
      "invalid_request",
      "지역 조회에는 region_name 또는 region_names가 필요합니다.",
    )

  if region_name is not None:
    return {"region_name": region_name}
  return {"region_names": region_names}


def normalize_area_policy(
  slots: TrendSlots,
  *,
  use_actual_complex_area: bool,
) -> dict[str, Any]:
  """㎡ 또는 평형 입력을 DAO용 전용면적 조건으로 정규화한다.

  단일 평형은 조회 대상에 따라 처리 방식이 다르다.

  - 단지 추이: 해당 단지의 실제 면적 목록 중 가장 가까운 값을 나중에 선택
  - 지역·순위: 여러 단지의 면적을 하나로 확정할 수 없으므로 예상값 ±1㎡
  """

  has_area = slots.area is not None
  has_area_range = slots.area_min is not None or slots.area_max is not None
  has_pyeong = slots.pyeong is not None
  has_pyeong_range = slots.pyeong_min is not None or slots.pyeong_max is not None

  if has_area and has_area_range:
    raise TrendPolicyError(
      "invalid_request",
      "단일 전용면적과 전용면적 범위를 함께 사용할 수 없습니다.",
    )
  if has_pyeong and has_pyeong_range:
    raise TrendPolicyError(
      "invalid_request",
      "단일 평형과 평형 범위를 함께 사용할 수 없습니다.",
    )
  if (has_area or has_area_range) and (has_pyeong or has_pyeong_range):
    raise TrendPolicyError(
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
      raise TrendPolicyError(
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
    estimated_area = estimate_exclusive_area(slots.pyeong)
    common_values = {
      "requested_pyeong": slots.pyeong,
      "estimated_exclusive_area": estimated_area,
      "exclusive_rate": ASSUMED_EXCLUSIVE_RATE,
    }

    if use_actual_complex_area:
      return {
        **common_values,
        "area_match_policy": "nearest_actual_exclusive_area",
      }

    return {
      **common_values,
      "area_min": estimated_area - SINGLE_AREA_TOLERANCE_SQM,
      "area_max": estimated_area + SINGLE_AREA_TOLERANCE_SQM,
      "area_match_policy": "estimated_area_plus_minus_1_sqm",
    }

  if has_pyeong_range:
    if slots.pyeong_min is None or slots.pyeong_max is None:
      raise TrendPolicyError(
        "invalid_request",
        "평형 범위는 최솟값과 최댓값을 모두 입력해야 합니다.",
      )
    if slots.pyeong_min > slots.pyeong_max:
      raise TrendPolicyError(
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
  """공급면적 평형을 75% 전용률 기준 예상 전용면적으로 변환한다."""

  return pyeong * PYEONG_TO_SQM * ASSUMED_EXCLUSIVE_RATE


def resolve_nearest_actual_area(
  estimated_area: float,
  actual_areas: Iterable[float],
) -> dict[str, Any]:
  """단일 평형과 가장 가까운 단지의 실제 전용면적을 선택한다."""

  _validate_positive_finite_number("estimated_area", estimated_area)

  normalized_areas: list[float] = []
  for actual_area in actual_areas:
    _validate_positive_finite_number("actual_area", actual_area)
    normalized_areas.append(float(actual_area))

  if not normalized_areas:
    raise TrendPolicyError(
      "no_result",
      "해당 단지에서 평형을 확인할 수 있는 거래 면적이 없습니다.",
    )

  # 차이가 같으면 작은 면적을 선택해 실행할 때마다 같은 결과가 나오게 한다.
  selected_area = min(
    normalized_areas,
    key=lambda actual_area: (abs(actual_area - estimated_area), actual_area),
  )
  difference = abs(selected_area - estimated_area)

  if difference > MAX_PYEONG_AREA_DIFFERENCE_SQM:
    raise TrendPolicyError(
      "unsupported_request",
      "입력 평형과 가까운 실제 전용면적을 찾지 못했습니다.",
    )

  return {
    "selected_exclusive_area": selected_area,
    "selected_area_difference": difference,
    "selected_area_tolerance": 0.011,
  }


def normalize_period_policy(
  slots: TrendSlots,
  *,
  base_date: date | str | None,
  default_period: str | None,
) -> dict[str, Any]:
  """상대 기간과 명시 날짜를 최종 시작일·종료일로 변환한다."""

  period = slots.period
  start_date = _parse_optional_date("start_date", slots.start_date)
  end_date = _parse_optional_date("end_date", slots.end_date)

  # price_ranking은 기간을 입력하지 않으면 보유 데이터 전체를 조회한다.
  # 이 경우에는 base_date도 필요하지 않다.
  if period is None and start_date is None and end_date is None:
    if default_period is None:
      return {
        "period": None,
        "start_date": None,
        "end_date": None,
        "base_date": None,
        "date_scope": "all_data",
      }
    period = default_period

  normalized_base_date = _require_base_date(base_date)

  if period is not None:
    parse_period(period)
  if period is not None and start_date is not None:
    raise TrendPolicyError(
      "invalid_request",
      "period와 start_date를 함께 사용할 수 없습니다.",
    )

  if start_date is not None and start_date > normalized_base_date:
    raise TrendPolicyError(
      "invalid_request",
      "조회 시작일이 보유 데이터의 최신일보다 미래입니다.",
    )
  if end_date is not None and end_date > normalized_base_date:
    end_date = normalized_base_date

  if start_date is not None and end_date is not None:
    if start_date > end_date:
      raise TrendPolicyError(
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


def normalize_interval(
  interval: str | None,
  *,
  start_date: str,
  end_date: str,
) -> str:
  """시계열 집계 간격을 검증하거나 조회 기간에 따라 자동 선택한다."""

  if interval is not None:
    if interval not in ALLOWED_INTERVALS:
      raise TrendPolicyError(
        "invalid_request",
        "interval은 month, quarter, year 중 하나여야 합니다.",
      )
    return interval

  start = date.fromisoformat(start_date)
  end = date.fromisoformat(end_date)

  if _is_within_calendar_months(start, end, 24):
    return "month"
  if _is_within_calendar_months(start, end, 60):
    return "quarter"
  return "year"


def normalize_change_direction(value: str | None) -> str:
  """변화율 순위 방향을 검증하고 기본값을 적용한다."""

  if value is None:
    return "up"
  if value not in ALLOWED_CHANGE_DIRECTIONS:
    raise TrendPolicyError(
      "invalid_request",
      "change_direction은 up, down, absolute 중 하나여야 합니다.",
    )
  return value


def normalize_rank_order(value: str | None) -> str:
  """실거래가 순위 방향을 검증하고 기본값을 적용한다."""

  if value is None:
    return "highest"
  if value not in ALLOWED_RANK_ORDERS:
    raise TrendPolicyError(
      "invalid_request",
      "rank_order는 highest 또는 lowest여야 합니다.",
    )
  return value


def normalize_ranking_limit(limit: int | None) -> int:
  """순위 결과 개수를 기본 5개, 최대 20개로 정규화한다."""

  if limit is None:
    return DEFAULT_RANKING_LIMIT
  if limit <= 0:
    raise TrendPolicyError(
      "invalid_request",
      "조회 개수는 1 이상이어야 합니다.",
    )
  return min(limit, MAX_RANKING_LIMIT)


def build_change_windows(start_date: str, end_date: str) -> dict[str, Any]:
  """전체 조회 기간에 맞춰 시작·종료 비교 window를 계산한다.

  두 window가 겹치면 같은 거래가 시작 가격과 종료 가격 양쪽에 포함되어
  변화율의 의미가 흐려진다. 따라서 계산한 시작 window의 종료일이 종료
  window의 시작일보다 빠른 경우에만 비교를 허용한다.
  """

  start = date.fromisoformat(start_date)
  end = date.fromisoformat(end_date)

  if _is_within_calendar_months(start, end, 6):
    window_months = 1
  elif _is_within_calendar_months(start, end, 18):
    window_months = 3
  elif _is_within_calendar_months(start, end, 36):
    window_months = 6
  else:
    window_months = 12

  start_window_end = add_calendar_months(start, window_months) - timedelta(days=1)
  end_window_start = subtract_calendar_months(end, window_months) + timedelta(days=1)
  normalized_start_window_end = min(start_window_end, end)
  normalized_end_window_start = max(end_window_start, start)

  if normalized_start_window_end >= normalized_end_window_start:
    raise TrendPolicyError(
      "invalid_request",
      "가격 변화율 비교에는 시작 구간과 종료 구간이 겹치지 않는 더 긴 기간이 필요합니다.",
    )

  return {
    "window_months": window_months,
    "start_window_start": start.isoformat(),
    "start_window_end": normalized_start_window_end.isoformat(),
    "end_window_start": normalized_end_window_start.isoformat(),
    "end_window_end": end.isoformat(),
  }


def parse_period(period: str) -> tuple[str, int]:
  """``2m`` 또는 ``3y``를 달력 단위와 숫자로 분리한다."""

  matched = PERIOD_PATTERN.fullmatch(period)
  if matched is None:
    raise TrendPolicyError(
      "invalid_request",
      "period는 양의 정수 뒤에 m(개월) 또는 y(년)를 붙여 입력해야 합니다.",
    )

  amount = int(matched.group("amount"))
  unit_code = matched.group("unit")

  if unit_code == "m":
    if amount > MAX_PERIOD_MONTHS:
      raise TrendPolicyError(
        "unsupported_request",
        f"개월 기간은 최대 {MAX_PERIOD_MONTHS}개월까지 지원합니다.",
      )
    return "month", amount

  if amount > MAX_PERIOD_YEARS:
    raise TrendPolicyError(
      "unsupported_request",
      f"연도 기간은 최대 {MAX_PERIOD_YEARS}년까지 지원합니다.",
    )
  return "year", amount


def subtract_calendar_period(value: date, period: str) -> date:
  """월말과 윤년을 보정하면서 상대 기간을 역산한다."""

  unit, amount = parse_period(period)
  months = amount if unit == "month" else amount * 12
  return subtract_calendar_months(value, months)


def add_calendar_months(value: date, months: int) -> date:
  """월말을 보정하면서 날짜에 달력 월을 더한다."""

  total_months = value.year * 12 + (value.month - 1) + months
  target_year, zero_based_month = divmod(total_months, 12)
  target_month = zero_based_month + 1
  target_day = min(
    value.day,
    calendar.monthrange(target_year, target_month)[1],
  )
  return date(target_year, target_month, target_day)


def subtract_calendar_months(value: date, months: int) -> date:
  """월말을 보정하면서 날짜에서 달력 월을 뺀다."""

  return add_calendar_months(value, -months)


def _default_period_for(query_type: TrendQueryType | str) -> str | None:
  """query_type별 기간 미입력 시 적용할 기본 기간을 반환한다."""

  if query_type in {
    TrendQueryType.COMPLEX_TREND,
    TrendQueryType.REGION_TREND,
  }:
    return DEFAULT_TREND_PERIOD
  if query_type == TrendQueryType.PRICE_CHANGE_RANKING:
    return DEFAULT_CHANGE_RANKING_PERIOD
  return None


def _validate_optional_interval(interval: str | None) -> None:
  """사용하지 않는 interval도 값 자체가 잘못됐으면 오류로 처리한다."""

  if interval is not None and interval not in ALLOWED_INTERVALS:
    raise TrendPolicyError(
      "invalid_request",
      "interval은 month, quarter, year 중 하나여야 합니다.",
    )


def _has_area_filter(criteria: dict[str, Any]) -> bool:
  """정규화 결과에 실제 면적 제한 조건이 있는지 확인한다."""

  return (
    criteria.get("area_min") is not None
    or criteria.get("area_max") is not None
    or criteria.get("estimated_exclusive_area") is not None
  )


def _normalize_optional_name(value: str | None) -> str | None:
  """단지명·지역명의 앞뒤 및 연속 공백을 정리한다."""

  if value is None:
    return None
  normalized = " ".join(value.split())
  return normalized or None


def _normalize_region_names(values: list[str] | None) -> list[str] | None:
  """복수 지역명을 정리하고 중복을 입력 순서대로 제거한다."""

  if values is None:
    return None
  if not values:
    raise TrendPolicyError(
      "invalid_request",
      "region_names에는 하나 이상의 지역명이 필요합니다.",
    )

  normalized_values: list[str] = []
  for value in values:
    normalized = _normalize_optional_name(value)
    if normalized is None:
      raise TrendPolicyError(
        "invalid_request",
        "region_names에 빈 지역명을 사용할 수 없습니다.",
      )
    if normalized not in normalized_values:
      normalized_values.append(normalized)
  return normalized_values


def _validate_all_numeric_slots(slots: TrendSlots) -> None:
  """면적과 평형 슬롯이 0보다 큰 유한 숫자인지 검사한다."""

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

  if slots.limit is not None and slots.limit <= 0:
    raise TrendPolicyError(
      "invalid_request",
      "조회 개수는 1 이상이어야 합니다.",
    )


def _validate_positive_finite_number(field_name: str, value: float) -> None:
  """숫자가 양수이며 NaN이나 무한대가 아닌지 확인한다."""

  if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
    raise TrendPolicyError(
      "invalid_request",
      f"{field_name}은 0보다 큰 유한 숫자여야 합니다.",
    )


def _parse_optional_date(field_name: str, value: str | None) -> date | None:
  """선택 날짜 문자열을 date로 변환한다."""

  if value is None:
    return None
  try:
    return date.fromisoformat(value)
  except (TypeError, ValueError) as error:
    raise TrendPolicyError(
      "invalid_request",
      f"{field_name}은 YYYY-MM-DD 형식이어야 합니다.",
    ) from error


def _require_base_date(value: date | str | None) -> date:
  """기간 계산에 필요한 데이터 기준일을 확인한다."""

  if value is None:
    raise ValueError("날짜 조건을 정규화하려면 base_date가 필요합니다.")
  if isinstance(value, date):
    return value
  try:
    return date.fromisoformat(value)
  except (TypeError, ValueError) as error:
    raise ValueError("base_date는 date 또는 YYYY-MM-DD 문자열이어야 합니다.") from error


def _is_within_calendar_months(start: date, end: date, months: int) -> bool:
  """종료일이 시작일로부터 지정한 달력 월 이내인지 확인한다."""

  return end <= add_calendar_months(start, months)


def _collect_present_slots(
  slots: TrendSlots,
  field_names: Iterable[str],
) -> dict[str, Any]:
  """입력된 값만 골라 ignored_slots에 기록한다."""

  return {
    field_name: getattr(slots, field_name)
    for field_name in field_names
    if getattr(slots, field_name) is not None
  }
