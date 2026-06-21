from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import Complex
from ..real_estate import complexes_for_parcel, trades_page, trend_for_complex_ids


def trades_by_parcel(
  session: Session,
  parcel_id: int,
  complex_id: int | None,
  page: int,
  size: int,
) -> dict[str, Any]:
  complex_ids = complexes_for_parcel(session, parcel_id, complex_id)
  return trades_page(session, parcel_id, complex_id, complex_ids, page, size)


def trades_by_complex(session: Session, complex_id: int, page: int, size: int) -> dict[str, Any] | None:
  complex_row = session.get(Complex, complex_id)
  if complex_row is None:
    return None
  return trades_page(session, complex_row.parcel_id, complex_id, [complex_id], page, size)


def trend_by_parcel(session: Session, parcel_id: int, complex_id: int | None) -> list[dict[str, Any]]:
  complex_ids = complexes_for_parcel(session, parcel_id, complex_id)
  return trend_for_complex_ids(session, complex_ids)


def trend_by_complex(session: Session, complex_id: int) -> list[dict[str, Any]] | None:
  if session.get(Complex, complex_id) is None:
    return None
  return trend_for_complex_ids(session, [complex_id])
