from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...database import get_session
from .dto import ComplexDetailResponse, ParcelComplexResponse
from .service import get_detail_by_complex, get_detail_by_parcel, list_parcel_complexes


router = APIRouter(prefix="/api/v1", tags=["complex"])


@router.get("/detail/{parcel_id}", response_model=ComplexDetailResponse)
def detail(
  parcel_id: int,
  complexId: int | None = None,
  session: Session = Depends(get_session),
) -> dict[str, Any]:
  item = get_detail_by_parcel(session, parcel_id, complexId)
  if item is None:
    raise HTTPException(status_code=404, detail="Complex not found")
  return item


@router.get("/detail/{parcel_id}/complexes", response_model=list[ParcelComplexResponse])
def parcel_complexes(parcel_id: int, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
  return list_parcel_complexes(session, parcel_id)


@router.get("/complex/{complex_id}", response_model=ComplexDetailResponse)
def complex_detail(complex_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
  item = get_detail_by_complex(session, complex_id)
  if item is None:
    raise HTTPException(status_code=404, detail="Complex not found")
  return item
