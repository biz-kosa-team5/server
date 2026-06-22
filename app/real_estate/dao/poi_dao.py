from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Poi


def station_pois(session: Session, name: str) -> list[Poi]:
  return list(session.scalars(
    select(Poi).where(Poi.category == "station", Poi.name == name)
  ).all())


def education_pois(session: Session, name: str | None = None, subtype: str | None = None) -> list[Poi]:
  statement = select(Poi).where(Poi.category == "education")
  if name is not None:
    statement = statement.where(Poi.name == name)
  if subtype is not None:
    statement = statement.where(Poi.subtype == subtype)
  return list(session.scalars(statement).all())


def pois_by_category(session: Session, category: str, subtype: str | None = None, name: str | None = None) -> list[Poi]:
  statement = select(Poi).where(Poi.category == category)
  if subtype is not None:
    statement = statement.where(Poi.subtype == subtype)
  if name is not None:
    statement = statement.where(Poi.name == name)
  return list(session.scalars(statement).all())
