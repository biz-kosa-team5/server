from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...database import get_session
from .dto import RegionComplexResponse, RegionDetailResponse, RegionSummaryResponse
from .service import get_region_detail, list_region_complexes, list_root_regions


router = APIRouter(prefix="/api/v1/region", tags=["region"])


@router.get("", response_model=list[RegionSummaryResponse])
def regions(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
  return list_root_regions(session)


@router.get("/{region_id}", response_model=RegionDetailResponse)
def region_detail(region_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
  region = get_region_detail(session, region_id)
  if region is None:
    raise HTTPException(status_code=404, detail="Region not found")
  return region


@router.get("/{region_id}/complexes", response_model=list[RegionComplexResponse])
def region_complexes(
  region_id: int,
  limit: int = Query(20, ge=1, le=100),
  offset: int = Query(0, ge=0),
  session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
  return list_region_complexes(session, region_id, limit, offset)
