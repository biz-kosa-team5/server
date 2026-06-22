from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_session
from app.real_estate.service.complex_service import detail_by_complex, detail_by_parcel, parcel_complexes


router = APIRouter(tags=["real-estate"])


@router.get("/detail/{parcel_id}")
def detail(
  parcel_id: int,
  complexId: int | None = None,
  session: Session = Depends(get_session),
) -> dict[str, Any]:
  item = detail_by_parcel(session, parcel_id, complexId)
  if item is None:
    raise HTTPException(status_code=404, detail="Complex not found")
  return item


@router.get("/detail/{parcel_id}/complexes")
def get_parcel_complexes(parcel_id: int, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
  return parcel_complexes(session, parcel_id)


@router.get("/complex/{complex_id}")
def get_complex_detail(complex_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
  item = detail_by_complex(session, complex_id)
  if item is None:
    raise HTTPException(status_code=404, detail="Complex not found")
  return item
