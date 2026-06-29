from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Poi
from app.real_estate.support import normalize_school_match_name, normalize_station_match_name, normalize_station_name


def station_pois(session: Session, name: str) -> list[Poi]:
  normalized_name = normalize_station_name(name)
  exact = list(session.scalars(
    select(Poi).where(Poi.category == "station", Poi.name == normalized_name)
  ).all())
  if exact:
    return exact
  return matching_pois_by_normalized_name(
    session,
    "station",
    name,
    normalize_station_match_name,
  )


def education_pois(session: Session, name: str | None = None, subtype: str | None = None) -> list[Poi]:
  statement = select(Poi).where(Poi.category == "education")
  if name is not None:
    statement = statement.where(Poi.name == name)
  if subtype is not None:
    statement = statement.where(Poi.subtype == subtype)
  exact = list(session.scalars(statement).all())
  if exact or name is None:
    return exact
  return matching_pois_by_normalized_name(
    session,
    "education",
    name,
    normalize_school_match_name,
    subtype=subtype,
  )


def pois_by_category(session: Session, category: str, subtype: str | None = None, name: str | None = None) -> list[Poi]:
  statement = select(Poi).where(Poi.category == category)
  if subtype is not None:
    statement = statement.where(Poi.subtype == subtype)
  if name is not None:
    statement = statement.where(Poi.name == name)
  return list(session.scalars(statement).all())


def matching_pois_by_normalized_name(
  session: Session,
  category: str,
  name: str,
  normalizer: Callable[[str | None], str | None],
  *,
  subtype: str | None = None,
) -> list[Poi]:
  target = normalizer(name)
  if target is None:
    return []

  statement = select(Poi).where(Poi.category == category)
  if subtype is not None:
    statement = statement.where(Poi.subtype == subtype)
  candidates = list(session.scalars(statement).all())

  exact_normalized = [
    poi
    for poi in candidates
    if normalizer(poi.name) == target
  ]
  if exact_normalized:
    return exact_normalized

  return [
    poi
    for poi in candidates
    if target in (normalizer(poi.name) or "") or (normalizer(poi.name) or "") in target
  ]
