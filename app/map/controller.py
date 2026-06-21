from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from ..database import get_session
from .dto import ComplexMarkerResponse, RegionMarkerResponse
from .service import list_complex_markers, list_region_markers


router = APIRouter(prefix="/api/v1/map", tags=["map"])


@router.post("/regions", response_model=list[RegionMarkerResponse])
def map_regions(
  payload: dict[str, Any] = Body(default={}),
  session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
  return list_region_markers(session, payload)


@router.post("/complexes", response_model=list[ComplexMarkerResponse])
def map_complexes(
  payload: dict[str, Any] = Body(default={}),
  session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
  return list_complex_markers(session, payload)
