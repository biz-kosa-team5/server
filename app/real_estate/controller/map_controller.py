from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_session
from app.real_estate.service.map_service import complex_markers, region_markers


router = APIRouter(tags=["real-estate"])


@router.post("/map/regions")
def map_regions(
  payload: dict[str, Any] = Body(default={}),
  session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
  try:
    return region_markers(session, payload)
  except ValueError as error:
    raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/map/complexes")
def map_complexes(
  payload: dict[str, Any] = Body(default={}),
  session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
  return complex_markers(session, payload)
