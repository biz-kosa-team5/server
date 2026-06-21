from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Complex, Region
from ..real_estate import clamp, complex_summary


def root_regions(session: Session) -> list[dict[str, Any]]:
  rows = session.scalars(
    select(Region).where(Region.parent_id.is_(None)).order_by(Region.name)
  ).all()
  return [{"id": row.id, "name": row.name} for row in rows]


def region_detail(session: Session, region_id: int) -> dict[str, Any] | None:
  row = session.get(Region, region_id)
  if row is None:
    return None

  children = session.scalars(
    select(Region).where(Region.parent_id == region_id).order_by(Region.name)
  ).all()
  return {
    "id": row.id,
    "name": row.name,
    "latitude": row.center_lat,
    "longitude": row.center_lng,
    "children": [{"id": child.id, "name": child.name} for child in children],
  }


def region_complexes(session: Session, region_id: int, limit: int, offset: int) -> list[dict[str, Any]]:
  rows = session.scalars(
    select(Complex)
    .where(Complex.region_id == region_id)
    .order_by(Complex.name)
    .limit(clamp(limit, 1, 100))
    .offset(max(offset, 0))
  ).all()
  return [complex_summary(row) for row in rows]
