from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_session
from app.real_estate.service.search_service import search_complexes, search_suggestions


router = APIRouter(tags=["real-estate"])


@router.get("/search/complexes/suggestions")
def complex_suggestions(
  q: str = Query(""),
  session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
  return search_suggestions(session, q)


@router.get("/search/complexes")
def complex_search(
  q: str = Query(""),
  session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
  return search_complexes(session, q)
