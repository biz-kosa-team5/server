from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import repository


def get_trades_by_parcel(
  session: Session,
  parcel_id: int,
  complex_id: int | None,
  page: int,
  size: int,
) -> dict[str, Any]:
  return repository.trades_by_parcel(session, parcel_id, complex_id, page, size)


def get_trades_by_complex(
  session: Session,
  complex_id: int,
  page: int,
  size: int,
) -> dict[str, Any] | None:
  return repository.trades_by_complex(session, complex_id, page, size)


def get_trend_by_parcel(
  session: Session,
  parcel_id: int,
  complex_id: int | None,
) -> list[dict[str, Any]]:
  return repository.trend_by_parcel(session, parcel_id, complex_id)


def get_trend_by_complex(session: Session, complex_id: int) -> list[dict[str, Any]] | None:
  return repository.trend_by_complex(session, complex_id)
