"""H4에서 사용하는 공통 DB 조회 기능.

단지와 지역 대상을 확정하는 검색 기능과 단지·지역 시계열 집계 기능을
담는다. 이후 가격 순위와 가격 변화율 순위도 같은 DAO에 추가한다.

DAO는 후보 목록을 조회할 뿐, 후보가 여러 개일 때 어떤 실패를 반환할지는
결정하지 않는다. 후보 수를 해석하는 업무 규칙은 Service가 담당한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Integer, case, cast, func, literal, or_, select
from sqlalchemy.orm import Session

from app.models import Complex, Region, Trade


@dataclass(slots=True)
class PriceChangeRankingQueryResult:
  """가격 변화율 DAO의 결과와 중간 판정 정보를 함께 전달한다.

  ``eligible_count``는 시작·종료 window의 최소 거래 건수를 충족한 단지
  수다. 이 값이 0이면 비교 데이터 부족이고, 0보다 크지만 ``items``가
  비었다면 데이터는 충분하지만 요청한 상승·하락 방향의 단지가 없는 것이다.
  """

  items: list[dict[str, Any]] = field(default_factory=list)
  eligible_count: int = 0


class PriceTrendDao:
  """SQLAlchemy Session을 주입받아 H4에 필요한 DB 조회를 수행한다."""

  def __init__(self, session: Session) -> None:
    self.session = session

  def find_exact_complexes(self, complex_name: str) -> list[Complex]:
    """단지명 또는 실거래 단지명이 정확히 일치하는 후보를 조회한다.

    검색할 때만 공백과 영문 대소문자를 무시한다. DB에 저장된 단지명
    원본은 수정하지 않는다.
    """

    normalized_name = _normalize_search_name(complex_name)
    statement = (
      select(Complex)
      .where(
        or_(
          _normalized_name_expression(Complex.name) == normalized_name,
          _normalized_name_expression(Complex.trade_name) == normalized_name,
        )
      )
      .order_by(Complex.name, Complex.id)
    )
    return list(self.session.scalars(statement).all())

  def find_partial_complexes(
    self,
    complex_name: str,
    *,
    limit: int = 20,
  ) -> list[Complex]:
    """정확히 일치하는 단지가 없을 때 이름이 포함된 후보를 조회한다."""

    normalized_name = _normalize_search_name(complex_name)
    pattern = f"%{_escape_like_pattern(normalized_name)}%"
    statement = (
      select(Complex)
      .where(
        or_(
          _normalized_name_expression(Complex.name).like(pattern, escape="\\"),
          _normalized_name_expression(Complex.trade_name).like(pattern, escape="\\"),
        )
      )
      .order_by(Complex.name, Complex.id)
      .limit(max(1, limit))
    )
    return list(self.session.scalars(statement).all())

  def find_exact_regions(self, region_name: str) -> list[Region]:
    """지역명이 정확히 일치하는 후보를 조회한다.

    지역은 Complex의 trade_name과 같은 별칭 컬럼이 없으므로
    ``regions.name``만 검색한다.
    """

    normalized_name = _normalize_search_name(region_name)
    statement = (
      select(Region)
      .where(_normalized_name_expression(Region.name) == normalized_name)
      .order_by(Region.name, Region.id)
    )
    return list(self.session.scalars(statement).all())

  def find_partial_regions(
    self,
    region_name: str,
    *,
    limit: int = 20,
  ) -> list[Region]:
    """정확히 일치하는 지역이 없을 때 이름이 포함된 후보를 조회한다."""

    normalized_name = _normalize_search_name(region_name)
    pattern = f"%{_escape_like_pattern(normalized_name)}%"
    statement = (
      select(Region)
      .where(
        _normalized_name_expression(Region.name).like(pattern, escape="\\")
      )
      .order_by(Region.name, Region.id)
      .limit(max(1, limit))
    )
    return list(self.session.scalars(statement).all())

  def find_max_deal_date(self) -> str | None:
    """전체 실거래 데이터의 최신 거래일을 반환한다.

    Policy에서 최근 1년·3년 같은 상대 기간을 실제 날짜 범위로 바꾸려면
    데이터 기준일이 필요하다. Service에 고정 base_date가 주입되지 않았을
    때만 이 함수를 사용한다.
    """

    return self.session.scalar(select(func.max(Trade.deal_date)))

  def find_distinct_areas(self, complex_id: int) -> list[float]:
    """특정 단지에서 실제 거래된 전용면적을 중복 없이 반환한다.

    단지 시세에서 사용자가 단일 평형을 입력한 경우 가장 가까운 실제
    전용면적을 선택하기 위해 사용한다.
    """

    statement = (
      select(Trade.excl_area)
      .where(Trade.complex_id == complex_id)
      .distinct()
      .order_by(Trade.excl_area)
    )
    return [float(area) for area in self.session.scalars(statement).all()]

  def find_complex_trend(
    self,
    complex_id: int,
    criteria: dict[str, Any],
  ) -> list[dict[str, Any]]:
    """특정 단지의 거래를 기간별로 묶어 시세 흐름을 반환한다.

    단지 확정은 Service에서 이미 끝났으므로 단지명이 아니라 DB 기본키인
    complex_id를 받는다. 기간과 면적은 Policy가 만든 criteria를 사용한다.
    """

    statement = select(Trade).where(Trade.complex_id == complex_id)
    return self._find_trend(statement, criteria)

  def find_region_trend(
    self,
    region_ids: list[int],
    criteria: dict[str, Any],
  ) -> list[dict[str, Any]]:
    """선택한 지역에 직접 연결된 모든 단지의 시세 흐름을 반환한다.

    현재 공통 DB에서 Complex.region_id는 강남구·서초구·송파구 같은 구
    Region을 직접 참조하므로 별도의 하위 지역 재귀 조회는 하지 않는다.
    """

    if not region_ids:
      return []

    statement = (
      select(Trade)
      .join(Complex, Trade.complex_id == Complex.id)
      .where(Complex.region_id.in_(region_ids))
    )
    return self._find_trend(statement, criteria)

  def find_price_ranking(
    self,
    region_ids: list[int],
    criteria: dict[str, Any],
  ) -> list[dict[str, Any]]:
    """지역 내 단지별 대표 거래를 비교해 최고가·최저가 순위를 반환한다.

    거래 행 전체를 바로 정렬하면 같은 단지의 여러 거래가 순위에 반복해서
    나타날 수 있다. 따라서 다음 두 단계로 조회한다.

    1. 각 단지 안에서 최고가 또는 최저가 거래 한 건 선택
    2. 단지별로 선택된 대표 거래끼리 다시 정렬해 최종 순위 계산
    """

    if not region_ids:
      return []

    rank_order = str(criteria["rank_order"])
    limit = int(criteria["limit"])

    if rank_order == "highest":
      # 같은 금액이면 최근 거래, 거래일까지 같으면 ID가 큰 거래를 대표로
      # 선택해 결과가 매번 동일하게 나오도록 한다.
      representative_order = (
        Trade.deal_amount.desc(),
        Trade.deal_date.desc(),
        Trade.id.desc(),
      )
    elif rank_order == "lowest":
      # 최저가 순위도 같은 금액에서는 오래된 거래와 작은 ID를 먼저 두어
      # 정렬 방향 전체를 일관되게 오름차순으로 사용한다.
      representative_order = (
        Trade.deal_amount.asc(),
        Trade.deal_date.asc(),
        Trade.id.asc(),
      )
    else:
      # Policy가 먼저 검증하므로 이 오류는 사용자 입력 오류가 아니라
      # Service와 DAO 사이의 연결 오류를 뜻한다.
      raise ValueError(f"지원하지 않는 rank_order입니다: {rank_order}")

    # ROW_NUMBER는 단지별 거래에 1, 2, 3... 번호를 붙인다. 단지마다
    # 1번 행만 남기면 단지별 대표 거래가 정확히 한 건씩 선택된다.
    complex_row_number = func.row_number().over(
      partition_by=Complex.id,
      order_by=representative_order,
    ).label("complex_row_number")

    representative_trades = (
      select(
        Complex.id.label("complex_id"),
        Complex.name.label("complex_name"),
        Complex.address.label("address"),
        Trade.id.label("trade_id"),
        Trade.deal_date.label("deal_date"),
        Trade.deal_amount.label("deal_amount"),
        Trade.excl_area.label("exclusive_area"),
        Trade.floor.label("floor"),
        Trade.apt_dong.label("apt_dong"),
        complex_row_number,
      )
      .join(Trade, Trade.complex_id == Complex.id)
      .where(Complex.region_id.in_(region_ids))
    )
    representative_trades = _apply_trade_filters(
      representative_trades,
      criteria,
    ).subquery()

    if rank_order == "highest":
      final_order = (
        representative_trades.c.deal_amount.desc(),
        representative_trades.c.deal_date.desc(),
        representative_trades.c.trade_id.desc(),
      )
    else:
      final_order = (
        representative_trades.c.deal_amount.asc(),
        representative_trades.c.deal_date.asc(),
        representative_trades.c.trade_id.asc(),
      )

    statement = (
      select(representative_trades)
      .where(representative_trades.c.complex_row_number == 1)
      .order_by(*final_order)
      .limit(limit)
    )
    rows = self.session.execute(statement).all()

    # rank는 SQL의 행 번호가 아니라 최종 정렬 결과의 위치이므로 Python에서
    # 1부터 부여해도 의미가 동일하고 반환 구조가 더 명확하다.
    return [
      {
        "rank": rank,
        "complex_id": int(row.complex_id),
        "complex_name": row.complex_name,
        "address": row.address,
        "trade_id": int(row.trade_id),
        "deal_date": str(row.deal_date),
        "deal_amount": int(row.deal_amount),
        "exclusive_area": float(row.exclusive_area),
        "floor": row.floor,
        "apt_dong": row.apt_dong,
      }
      for rank, row in enumerate(rows, start=1)
    ]

  def find_price_change_ranking(
    self,
    region_ids: list[int],
    criteria: dict[str, Any],
  ) -> PriceChangeRankingQueryResult:
    """지역 내 단지별 시작·종료 가격을 비교해 변화율 순위를 반환한다.

    단지마다 다음 값을 계산한다.

    - 시작 window의 평균 ㎡당 가격과 거래 건수
    - 종료 window의 평균 ㎡당 가격과 거래 건수
    - 두 가격의 증감액과 변화율

    시작과 종료 window 모두 최소 거래 건수를 충족한 단지만 순위 후보가
    된다. 중간 기간의 거래는 전체 조회 기간을 설명할 때는 의미가 있지만,
    시작점과 종료점의 가격 비교에는 사용하지 않는다.
    """

    if not region_ids:
      return PriceChangeRankingQueryResult()

    start_condition = Trade.deal_date.between(
      str(criteria["start_window_start"]),
      str(criteria["start_window_end"]),
    )
    end_condition = Trade.deal_date.between(
      str(criteria["end_window_start"]),
      str(criteria["end_window_end"]),
    )
    window_condition = or_(start_condition, end_condition)
    price_per_sqm = Trade.deal_amount / func.nullif(Trade.excl_area, 0)

    # CASE는 각 거래가 시작 window인지 종료 window인지 구분한다.
    # 해당하지 않는 행은 NULL이 되고 AVG와 COUNT 집계에서 제외된다.
    start_price = func.avg(
      case((start_condition, price_per_sqm), else_=None)
    ).label("start_avg_price_per_sqm")
    end_price = func.avg(
      case((end_condition, price_per_sqm), else_=None)
    ).label("end_avg_price_per_sqm")
    start_count = func.count(
      case((start_condition, Trade.id), else_=None)
    ).label("start_trade_count")
    end_count = func.count(
      case((end_condition, Trade.id), else_=None)
    ).label("end_trade_count")

    statement = (
      select(
        Complex.id.label("complex_id"),
        Complex.name.label("complex_name"),
        Complex.address.label("address"),
        start_price,
        end_price,
        start_count,
        end_count,
        func.avg(Trade.excl_area).label("avg_exclusive_area"),
      )
      .join(Trade, Trade.complex_id == Complex.id)
      .where(Complex.region_id.in_(region_ids))
      .where(window_condition)
    )
    statement = _apply_area_filters(statement, criteria)
    statement = (
      statement
      .group_by(Complex.id, Complex.name, Complex.address)
      .having(start_count >= int(criteria["min_trade_count"]))
      .having(end_count >= int(criteria["min_trade_count"]))
      .having(start_price > 0)
    )

    rows = self.session.execute(statement).all()
    candidates: list[dict[str, Any]] = []
    for row in rows:
      start_value = float(row.start_avg_price_per_sqm)
      end_value = float(row.end_avg_price_per_sqm)
      change_amount = end_value - start_value
      change_rate = (change_amount / start_value) * 100

      candidates.append({
        "complex_id": int(row.complex_id),
        "complex_name": row.complex_name,
        "address": row.address,
        "start_avg_price_per_sqm": round(start_value, 2),
        "end_avg_price_per_sqm": round(end_value, 2),
        "change_amount": round(change_amount, 2),
        # 필터와 정렬에는 반올림 전 값을 사용한다. 아주 작은 상승률이
        # 0.00으로 반올림되어 상승 대상에서 사라지는 일을 방지한다.
        "_raw_change_rate": change_rate,
        "start_trade_count": int(row.start_trade_count),
        "end_trade_count": int(row.end_trade_count),
        "avg_exclusive_area": round(float(row.avg_exclusive_area), 2),
      })

    eligible_count = len(candidates)
    direction = str(criteria["change_direction"])
    if direction == "up":
      candidates = [
        row for row in candidates
        if row["_raw_change_rate"] > 0
      ]
      candidates.sort(
        key=lambda row: (-row["_raw_change_rate"], row["complex_id"])
      )
    elif direction == "down":
      candidates = [
        row for row in candidates
        if row["_raw_change_rate"] < 0
      ]
      candidates.sort(
        key=lambda row: (row["_raw_change_rate"], row["complex_id"])
      )
    elif direction == "absolute":
      candidates = [
        row for row in candidates
        if row["_raw_change_rate"] != 0
      ]
      candidates.sort(
        key=lambda row: (-abs(row["_raw_change_rate"]), row["complex_id"])
      )
    else:
      raise ValueError(f"지원하지 않는 change_direction입니다: {direction}")

    limited = candidates[:int(criteria["limit"])]
    items = []
    for rank, row in enumerate(limited, start=1):
      raw_change_rate = row.pop("_raw_change_rate")
      items.append({
        "rank": rank,
        **row,
        "change_rate": round(raw_change_rate, 2),
      })

    return PriceChangeRankingQueryResult(
      items=items,
      eligible_count=eligible_count,
    )

  def _find_trend(
    self,
    trade_statement,
    criteria: dict[str, Any],
  ) -> list[dict[str, Any]]:
    """단지·지역 시계열 조회가 공유하는 집계 SQL을 실행한다.

    입력 statement에는 조회 대상 단지 범위만 들어 있다. 여기에서 기간과
    면적 조건을 추가하고, 월·분기·연도별 집계 SQL로 바꾼다.
    """

    interval = str(criteria["interval"])
    period_expression = _period_start_expression(interval)

    # ㎡당 가격은 각 거래의 거래금액을 전용면적으로 나눈 뒤 평균낸다.
    # NULLIF는 혹시 모를 0㎡ 데이터 때문에 DB에서 0으로 나누는 오류가
    # 발생하지 않도록 보호한다.
    price_per_sqm = Trade.deal_amount / func.nullif(Trade.excl_area, 0)

    # 기존 select(Trade)의 대상 조건을 유지하면서 집계할 컬럼으로 교체한다.
    statement = trade_statement.with_only_columns(
      period_expression.label("period_start"),
      func.avg(Trade.deal_amount).label("avg_deal_amount"),
      func.avg(price_per_sqm).label("avg_price_per_sqm"),
      func.min(Trade.deal_amount).label("min_deal_amount"),
      func.max(Trade.deal_amount).label("max_deal_amount"),
      func.count(Trade.id).label("trade_count"),
      func.avg(Trade.excl_area).label("avg_exclusive_area"),
      maintain_column_froms=True,
    )
    statement = _apply_trade_filters(statement, criteria)
    statement = (
      statement
      .group_by(period_expression)
      .order_by(period_expression)
    )

    rows = self.session.execute(statement).all()
    return [
      {
        "period_start": str(row.period_start),
        "avg_deal_amount": round(float(row.avg_deal_amount), 2),
        "avg_price_per_sqm": round(float(row.avg_price_per_sqm), 2),
        "min_deal_amount": int(row.min_deal_amount),
        "max_deal_amount": int(row.max_deal_amount),
        "trade_count": int(row.trade_count),
        "avg_exclusive_area": round(float(row.avg_exclusive_area), 2),
      }
      for row in rows
    ]


def _apply_trade_filters(statement, criteria: dict[str, Any]):
  """Policy가 만든 기간 및 면적 조건을 거래 조회문에 적용한다."""

  start_date = criteria.get("start_date")
  end_date = criteria.get("end_date")
  if start_date is not None:
    statement = statement.where(Trade.deal_date >= str(start_date))
  if end_date is not None:
    statement = statement.where(Trade.deal_date <= str(end_date))

  return _apply_area_filters(statement, criteria)


def _apply_area_filters(statement, criteria: dict[str, Any]):
  """Policy가 만든 면적 조건만 조회문에 적용한다."""

  # 단일 평형을 단지의 실제 면적으로 확정한 경우에는 부동소수점 완전
  # 일치 대신 Policy가 정한 작은 허용 오차를 사용한다.
  selected_area = criteria.get("selected_exclusive_area")
  if selected_area is not None:
    tolerance = float(criteria.get("selected_area_tolerance", 0.011))
    return statement.where(
      func.abs(Trade.excl_area - float(selected_area)) <= tolerance
    )

  area_min = criteria.get("area_min")
  area_max = criteria.get("area_max")
  if area_min is not None:
    statement = statement.where(Trade.excl_area >= float(area_min))
  if area_max is not None:
    statement = statement.where(Trade.excl_area <= float(area_max))
  return statement


def _period_start_expression(interval: str):
  """TEXT 거래일을 월·분기·연도 시작일 문자열로 변환한다.

  현재 deal_date가 ``YYYY-MM-DD`` TEXT이므로 문자열 일부를 이용하면
  SQLite 테스트 DB와 PostgreSQL 운영 DB에서 같은 방식으로 동작한다.

  예:
  - month   → 2026-05-01
  - quarter → 2026-04-01
  - year    → 2026-01-01
  """

  year = func.substr(Trade.deal_date, 1, 4)

  if interval == "month":
    return func.substr(Trade.deal_date, 1, 7) + literal("-01")

  if interval == "quarter":
    month = cast(func.substr(Trade.deal_date, 6, 2), Integer)
    quarter_start_month = case(
      (month <= 3, "01"),
      (month <= 6, "04"),
      (month <= 9, "07"),
      else_="10",
    )
    return year + literal("-") + quarter_start_month + literal("-01")

  if interval == "year":
    return year + literal("-01-01")

  # interval은 Policy에서 먼저 검증되므로 여기까지 오면 계층 연결 오류다.
  raise ValueError(f"지원하지 않는 interval입니다: {interval}")


def _normalize_search_name(value: str) -> str:
  """검색 비교용으로 공백을 제거하고 영문을 소문자로 바꾼다."""

  return "".join(value.lower().split())


def _escape_like_pattern(value: str) -> str:
  """사용자 입력의 LIKE 와일드카드를 일반 문자로 처리한다."""

  return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _normalized_name_expression(column):
  """DB 문자열에서 공백을 제거하고 소문자로 만드는 SQL 표현식."""

  return func.lower(func.replace(func.coalesce(column, ""), " ", ""))
