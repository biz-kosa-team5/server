"""H1 단순조회에서 사용하는 DB 조회 기능.

DAO는 SQLAlchemy를 이용해 공통 DB에서 Entity를 조회하는 역할만 한다.
입력값의 의미 검증과 기간·면적 계산은 Policy가 담당하고, Entity를
LocationData/TradeData로 변환하는 작업은 이후 Service 계층이 담당한다.

이렇게 계층을 나누면 DAO는 "어떤 조건으로 어떤 데이터를 가져오는가"에만
집중할 수 있고, 자연어 해석이나 응답 문장 생성과 섞이지 않는다.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Complex, Trade


class SimpleLookupDao:
  """SQLAlchemy Session을 주입받아 H1에 필요한 조회를 수행한다."""

  def __init__(self, session: Session) -> None:
    self.session = session

  def find_exact_complexes(self, complex_name: str) -> list[Complex]:
    """단지명 또는 실거래 단지명이 정확히 일치하는 후보를 조회한다.

    사용자는 "잠실 엘스", DB는 "잠실엘스"처럼 공백을 다르게 입력할 수
    있으므로 검색할 때만 공백을 제거한다. DB에 저장된 원본 이름은 수정하지
    않는다. 영문이 섞인 이름도 비교할 수 있도록 소문자 변환을 함께 적용한다.
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
    """정확 일치 후보가 없을 때 이름 일부가 포함된 단지를 조회한다.

    부분 일치는 후보 안내를 위한 보조 검색이다. 너무 많은 결과가 상위
    에이전트에 전달되지 않도록 기본 20건으로 제한한다.
    """

    normalized_name = _normalize_search_name(complex_name)

    # SQL LIKE에서 %, _는 각각 여러 글자와 한 글자를 뜻하는 와일드카드다.
    # 사용자 입력에 이런 문자가 포함돼도 검색 문법이 아니라 단지명 문자
    # 자체로 취급하도록 escape 처리한다.
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

  def find_max_deal_date(self) -> str | None:
    """전체 실거래 데이터에서 가장 최신 거래일을 반환한다.

    현재 공통 DB의 deal_date는 `YYYY-MM-DD` 형식 TEXT다. 이 형식이
    유지되는 동안 문자열 MAX 결과는 날짜 MAX 결과와 동일하게 동작한다.
    """

    return self.session.scalar(select(func.max(Trade.deal_date)))

  def find_distinct_areas(self, complex_id: int) -> list[float]:
    """특정 단지에서 실제 거래된 전용면적 목록을 오름차순으로 반환한다."""

    statement = (
      select(Trade.excl_area)
      .where(Trade.complex_id == complex_id)
      .distinct()
      .order_by(Trade.excl_area)
    )
    return [float(area) for area in self.session.scalars(statement).all()]

  def find_trade_history(
    self,
    complex_id: int,
    criteria: dict[str, Any],
  ) -> list[Trade]:
    """정규화된 조건에 맞는 실거래 내역을 최신순으로 조회한다."""

    statement = select(Trade).where(Trade.complex_id == complex_id)
    statement = _apply_trade_filters(statement, criteria)
    statement = statement.order_by(Trade.deal_date.desc(), Trade.id.desc())
    statement = statement.limit(int(criteria.get("limit", 5)))
    return list(self.session.scalars(statement).all())

  def find_record_high(
    self,
    complex_id: int,
    criteria: dict[str, Any],
  ) -> Trade | None:
    """정규화된 조건 안에서 명목 거래금액이 가장 큰 거래 한 건을 조회한다.

    거래금액이 같으면 더 최근 거래를, 거래일도 같으면 ID가 큰 거래를
    선택해 항상 같은 결과가 나오도록 한다.
    """

    statement = select(Trade).where(Trade.complex_id == complex_id)
    statement = _apply_trade_filters(statement, criteria)
    statement = (
      statement
      .order_by(Trade.deal_amount.desc(), Trade.deal_date.desc(), Trade.id.desc())
      .limit(1)
    )
    return self.session.scalar(statement)


def _apply_trade_filters(statement, criteria: dict[str, Any]):
  """Policy가 만든 공통 기간·면적 조건을 거래 조회문에 적용한다."""

  start_date = criteria.get("start_date")
  end_date = criteria.get("end_date")
  if start_date is not None:
    statement = statement.where(Trade.deal_date >= start_date)
  if end_date is not None:
    statement = statement.where(Trade.deal_date <= end_date)

  # 단일 평형은 단지의 실제 전용면적 하나를 먼저 확정한다. 이 경우에는
  # 부동소수점 등가 비교 대신 Policy가 정한 허용 오차를 사용한다.
  selected_area = criteria.get("selected_exclusive_area")
  if selected_area is not None:
    tolerance = float(criteria.get("selected_area_tolerance", 0.011))
    statement = statement.where(
      func.abs(Trade.excl_area - float(selected_area)) <= tolerance
    )
    return statement

  area_min = criteria.get("area_min")
  area_max = criteria.get("area_max")
  if area_min is not None:
    statement = statement.where(Trade.excl_area >= float(area_min))
  if area_max is not None:
    statement = statement.where(Trade.excl_area <= float(area_max))
  return statement


def _normalize_search_name(value: str) -> str:
  """단지 검색에 사용할 비교 문자열을 만든다."""

  return "".join(value.lower().split())


def _escape_like_pattern(value: str) -> str:
  """SQL LIKE의 escape 문자와 와일드카드를 일반 문자로 바꾼다.

  처리 순서가 중요하다. 먼저 escape 문자 자체를 두 번 쓰고, 그다음
  `%`와 `_` 앞에 escape 문자를 붙여야 이미 추가한 문자를 다시 변경하지
  않는다.
  """

  return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _normalized_name_expression(column):
  """DB 단지명에서 공백을 제거하고 소문자로 만드는 SQL 표현식."""

  return func.lower(func.replace(func.coalesce(column, ""), " ", ""))
