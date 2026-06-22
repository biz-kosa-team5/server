from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.real_estate.dao import child_regions, complexes_by_region, get_region, root_regions as select_root_regions
from app.real_estate.support import clamp, complex_summary


def root_regions(session: Session) -> list[dict[str, Any]]:
  return [{"id": row.id, "name": row.name} for row in select_root_regions(session)]


def region_detail(session: Session, region_id: int) -> dict[str, Any] | None:
  row = get_region(session, region_id)
  if row is None:
    return None

  children = child_regions(session, region_id)
  return {
    "id": row.id,
    "name": row.name,
    "latitude": row.center_lat,
    "longitude": row.center_lng,
    "children": [{"id": child.id, "name": child.name} for child in children],
  }


def region_complexes(session: Session, region_id: int, limit: int, offset: int) -> list[dict[str, Any]]:
  rows = complexes_by_region(session, region_id, clamp(limit, 1, 100), max(offset, 0))
  return [complex_summary(row) for row in rows]
