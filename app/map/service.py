from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import repository


def list_region_markers(session: Session, payload: dict[str, Any]) -> list[dict[str, Any]]:
  return repository.region_markers(session, payload)


def list_complex_markers(session: Session, payload: dict[str, Any]) -> list[dict[str, Any]]:
  return repository.complex_markers(session, payload)
