from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import repository


def suggest_complexes(session: Session, query: str) -> list[dict[str, Any]]:
  return repository.search_suggestions(session, query)


def search_complexes(session: Session, query: str) -> list[dict[str, Any]]:
  return repository.search_complexes(session, query)
