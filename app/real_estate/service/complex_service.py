from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.real_estate.dao import (
  complexes_by_parcel,
  get_complex,
  get_complex_by_parcel_and_id,
  get_first_complex_by_parcel,
)
from app.real_estate.support import complex_detail, complex_summary


def detail_by_parcel(
  session: Session,
  parcel_id: int,
  complex_id: int | None = None,
) -> dict[str, Any] | None:
  row = (
    get_complex_by_parcel_and_id(session, parcel_id, complex_id)
    if complex_id is not None
    else get_first_complex_by_parcel(session, parcel_id)
  )
  return None if row is None else complex_detail(row)


def detail_by_complex(session: Session, complex_id: int) -> dict[str, Any] | None:
  row = get_complex(session, complex_id)
  return None if row is None else complex_detail(row)


def parcel_complexes(session: Session, parcel_id: int) -> list[dict[str, Any]]:
  return [complex_summary(row) for row in complexes_by_parcel(session, parcel_id)]
