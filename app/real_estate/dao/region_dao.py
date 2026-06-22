from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Region


def regions_in_bounds(session: Session, bounds: dict[str, float]) -> list[Region]:
  return list(session.scalars(
    select(Region)
    .where(Region.center_lat.between(bounds["swLat"], bounds["neLat"]))
    .where(Region.center_lng.between(bounds["swLng"], bounds["neLng"]))
    .order_by(Region.name)
  ).all())


def root_regions(session: Session) -> list[Region]:
  return list(session.scalars(
    select(Region).where(Region.parent_id.is_(None)).order_by(Region.name)
  ).all())


def get_region(session: Session, region_id: int) -> Region | None:
  return session.get(Region, region_id)


def child_regions(session: Session, region_id: int) -> list[Region]:
  return list(session.scalars(
    select(Region).where(Region.parent_id == region_id).order_by(Region.name)
  ).all())
