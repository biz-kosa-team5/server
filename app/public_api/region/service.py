from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import repository


def list_root_regions(session: Session) -> list[dict[str, Any]]:
  return repository.root_regions(session)


def get_region_detail(session: Session, region_id: int) -> dict[str, Any] | None:
  return repository.region_detail(session, region_id)


def list_region_complexes(session: Session, region_id: int, limit: int, offset: int) -> list[dict[str, Any]]:
  return repository.region_complexes(session, region_id, limit, offset)
