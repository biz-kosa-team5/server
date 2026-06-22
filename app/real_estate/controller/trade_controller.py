from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_session
from app.real_estate.service.trade_service import (
  trades_by_complex,
  trades_by_parcel,
  trend_by_complex,
  trend_by_parcel,
)


router = APIRouter(tags=["real-estate"])


@router.get("/trade/{parcel_id}")
def parcel_trades(
  parcel_id: int,
  complexId: int | None = None,
  page: int = Query(0, ge=0),
  size: int = Query(20, ge=1, le=100),
  session: Session = Depends(get_session),
) -> dict[str, Any]:
  return trades_by_parcel(session, parcel_id, complexId, page, size)


@router.get("/trade/{parcel_id}/trend")
def parcel_trend(
  parcel_id: int,
  complexId: int | None = None,
  session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
  return trend_by_parcel(session, parcel_id, complexId)


@router.get("/complex/{complex_id}/trades")
def complex_trades(
  complex_id: int,
  page: int = Query(0, ge=0),
  size: int = Query(20, ge=1, le=100),
  session: Session = Depends(get_session),
) -> dict[str, Any]:
  item = trades_by_complex(session, complex_id, page, size)
  if item is None:
    raise HTTPException(status_code=404, detail="Complex not found")
  return item


@router.get("/complex/{complex_id}/trade-trend")
def complex_trend(complex_id: int, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
  trend = trend_by_complex(session, complex_id)
  if trend is None:
    raise HTTPException(status_code=404, detail="Complex not found")
  return trend
