from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_session
from app.real_estate.service.region_service import region_complexes, region_detail, root_regions


router = APIRouter(tags=["real-estate"])


@router.get("/region")
def regions(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
  return root_regions(session)


@router.get("/region/{region_id}")
def get_region_detail(region_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
  region = region_detail(session, region_id)
  if region is None:
    raise HTTPException(status_code=404, detail="Region not found")
  return region


@router.get("/region/{region_id}/complexes")
def get_region_complexes(
  region_id: int,
  limit: int = Query(20, ge=1, le=100),
  offset: int = Query(0, ge=0),
  session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
  return region_complexes(session, region_id, limit, offset)
