from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Complex
from ..real_estate import complex_detail, complex_summary


def detail_by_parcel(
  session: Session,
  parcel_id: int,
  complex_id: int | None = None,
) -> dict[str, Any] | None:
  statement = select(Complex).where(Complex.parcel_id == parcel_id).order_by(Complex.id).limit(1)
  if complex_id is not None:
    statement = select(Complex).where(Complex.parcel_id == parcel_id, Complex.id == complex_id)
  row = session.scalar(statement)
  return None if row is None else complex_detail(row)


def detail_by_complex(session: Session, complex_id: int) -> dict[str, Any] | None:
  row = session.get(Complex, complex_id)
  return None if row is None else complex_detail(row)


def parcel_complexes(session: Session, parcel_id: int) -> list[dict[str, Any]]:
  rows = session.scalars(
    select(Complex).where(Complex.parcel_id == parcel_id).order_by(Complex.name)
  ).all()
  return [complex_summary(row) for row in rows]
