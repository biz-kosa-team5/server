from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import repository


def get_detail_by_parcel(
  session: Session,
  parcel_id: int,
  complex_id: int | None = None,
) -> dict[str, Any] | None:
  return repository.detail_by_parcel(session, parcel_id, complex_id)


def get_detail_by_complex(session: Session, complex_id: int) -> dict[str, Any] | None:
  return repository.detail_by_complex(session, complex_id)


def list_parcel_complexes(session: Session, parcel_id: int) -> list[dict[str, Any]]:
  return repository.parcel_complexes(session, parcel_id)
