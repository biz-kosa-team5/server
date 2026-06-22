from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Complex


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
