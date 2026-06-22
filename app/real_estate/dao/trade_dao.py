from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Complex, Trade


def latest_trade_for_complex(session: Session, complex_id: int) -> Trade | None:
  return session.scalar(
    select(Trade)
    .where(Trade.complex_id == complex_id)
    .order_by(Trade.deal_date.desc(), Trade.id.desc())
    .limit(1)
  )


def complexes_for_parcel(session: Session, parcel_id: int, complex_id: int | None) -> list[int]:
  statement = select(Complex.id).where(Complex.parcel_id == parcel_id)
  if complex_id is not None:
    statement = statement.where(Complex.id == complex_id)
  return list(session.scalars(statement).all())


def count_trades_for_complex_ids(session: Session, complex_ids: list[int]) -> int:
  return session.scalar(
    select(func.count()).select_from(Trade).where(Trade.complex_id.in_(complex_ids))
  ) or 0


def trades_for_complex_ids(session: Session, complex_ids: list[int], page: int, size: int) -> list[Trade]:
  return list(session.scalars(
    select(Trade)
    .where(Trade.complex_id.in_(complex_ids))
    .order_by(Trade.deal_date.desc(), Trade.id.desc())
    .limit(size)
    .offset(page * size)
  ).all())


def monthly_trade_stats(session: Session, complex_ids: list[int]):
  month_expr = func.substr(Trade.deal_date, 1, 7)
  return session.execute(
    select(
      month_expr.label("month"),
      func.avg(Trade.deal_amount).label("avg_amount"),
      func.count().label("trade_count"),
      func.min(Trade.deal_amount).label("min_amount"),
      func.max(Trade.deal_amount).label("max_amount"),
    )
    .where(Trade.complex_id.in_(complex_ids))
    .group_by(month_expr)
    .order_by("month")
  ).all()
