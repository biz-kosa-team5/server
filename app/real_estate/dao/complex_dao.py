from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Complex, Poi


EARTH_RADIUS_M = 6371000


def complexes_in_bounds(session: Session, bounds: dict[str, float]) -> list[Complex]:
  return list(session.scalars(
    select(Complex)
    .where(Complex.latitude.is_not(None))
    .where(Complex.longitude.is_not(None))
    .where(Complex.latitude.between(bounds["swLat"], bounds["neLat"]))
    .where(Complex.longitude.between(bounds["swLng"], bounds["neLng"]))
    .order_by(Complex.name)
  ).all())


def search_complexes_by_text(session: Session, query: str, limit: int) -> list[Complex]:
  pattern = f"%{query}%"
  return list(session.scalars(
    select(Complex)
    .where(or_(Complex.name.like(pattern), Complex.trade_name.like(pattern), Complex.address.like(pattern)))
    .order_by(Complex.name)
    .limit(limit)
  ).all())


def complexes_by_region(session: Session, region_id: int, limit: int, offset: int) -> list[Complex]:
  return list(session.scalars(
    select(Complex)
    .where(Complex.region_id == region_id)
    .order_by(Complex.name)
    .limit(limit)
    .offset(offset)
  ).all())


def get_complex(session: Session, complex_id: int) -> Complex | None:
  return session.get(Complex, complex_id)


def get_first_complex_by_parcel(session: Session, parcel_id: int) -> Complex | None:
  return session.scalar(
    select(Complex).where(Complex.parcel_id == parcel_id).order_by(Complex.id).limit(1)
  )


def get_complex_by_parcel_and_id(session: Session, parcel_id: int, complex_id: int) -> Complex | None:
  return session.scalar(
    select(Complex).where(Complex.parcel_id == parcel_id, Complex.id == complex_id)
  )


def complexes_by_parcel(session: Session, parcel_id: int) -> list[Complex]:
  return list(session.scalars(
    select(Complex).where(Complex.parcel_id == parcel_id).order_by(Complex.name)
  ).all())


def all_complexes_ordered(session: Session) -> list[Complex]:
  return list(session.scalars(select(Complex).order_by(Complex.name)).all())


def complexes_near_pois_by_query(
  session: Session,
  pois: list[Poi],
  max_distance_m: int,
  complex_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
  poi_ids = [poi.id for poi in pois]
  if not poi_ids or complex_ids == []:
    return []

  distance_expr = haversine_distance_expr(
    Complex.latitude,
    Complex.longitude,
    Poi.latitude,
    Poi.longitude,
  )
  statement = (
    select(Complex, Poi, distance_expr.label("distance_m"))
    .join(Poi, Poi.id.in_(poi_ids))
    .where(Complex.latitude.is_not(None))
    .where(Complex.longitude.is_not(None))
    .where(distance_expr <= max_distance_m)
    .order_by(distance_expr)
  )
  if complex_ids is not None:
    statement = statement.where(Complex.id.in_(complex_ids))

  nearest_by_complex_id: dict[int, dict[str, Any]] = {}
  for complex_row, poi, distance_m in session.execute(statement).all():
    if complex_row.id in nearest_by_complex_id:
      continue
    nearest_by_complex_id[complex_row.id] = {
      "complex": complex_row,
      "matchedPoi": {
        "id": poi.id,
        "category": poi.category,
        "name": poi.name,
        "subtype": poi.subtype,
        "latitude": poi.latitude,
        "longitude": poi.longitude,
        "distanceM": round(float(distance_m), 2),
      },
    }
  return list(nearest_by_complex_id.values())


def haversine_distance_expr(lat1, lon1, lat2, lon2):
  return EARTH_RADIUS_M * 2 * func.asin(
    func.sqrt(
      func.pow(func.sin(func.radians(lat2 - lat1) / 2), 2)
      + func.cos(func.radians(lat1))
      * func.cos(func.radians(lat2))
      * func.pow(func.sin(func.radians(lon2 - lon1) / 2), 2)
    )
  )


def find_complex_by_name(session: Session, name: str) -> Complex | None:
  exact = session.scalar(
    select(Complex)
    .where(or_(Complex.name == name, Complex.trade_name == name))
    .order_by(Complex.id)
    .limit(1)
  )
  if exact is not None:
    return exact

  pattern = f"%{name}%"
  return session.scalar(
    select(Complex)
    .where(or_(Complex.name.like(pattern), Complex.trade_name.like(pattern)))
    .order_by(Complex.name)
    .limit(1)
  )
