from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...database import get_session
from .dto import ComplexSearchResponse, ComplexSuggestionResponse
from .service import search_complexes, suggest_complexes


router = APIRouter(prefix="/api/v1/search/complexes", tags=["search"])


@router.get("/suggestions", response_model=list[ComplexSuggestionResponse])
def complex_suggestions(
  q: str = Query(""),
  session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
  return suggest_complexes(session, q)


@router.get("", response_model=list[ComplexSearchResponse])
def complex_search(
  q: str = Query(""),
  session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
  return search_complexes(session, q)
