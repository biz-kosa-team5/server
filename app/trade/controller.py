from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_session
from .dto import TradePageResponse, TradeTrendPointResponse
from .service import (
  get_trades_by_complex,
  get_trades_by_parcel,
  get_trend_by_complex,
  get_trend_by_parcel,
)


router = APIRouter(prefix="/api/v1", tags=["trade"])


@router.get("/trade/{parcel_id}", response_model=TradePageResponse)
def parcel_trades(
  parcel_id: int,
  complexId: int | None = None,
  page: int = Query(0, ge=0),
  size: int = Query(20, ge=1, le=100),
  session: Session = Depends(get_session),
) -> dict[str, Any]:
  return get_trades_by_parcel(session, parcel_id, complexId, page, size)


@router.get("/trade/{parcel_id}/trend", response_model=list[TradeTrendPointResponse])
def parcel_trend(
  parcel_id: int,
  complexId: int | None = None,
  session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
  return get_trend_by_parcel(session, parcel_id, complexId)


@router.get("/complex/{complex_id}/trades", response_model=TradePageResponse)
def complex_trades(
  complex_id: int,
  page: int = Query(0, ge=0),
  size: int = Query(20, ge=1, le=100),
  session: Session = Depends(get_session),
) -> dict[str, Any]:
  item = get_trades_by_complex(session, complex_id, page, size)
  if item is None:
    raise HTTPException(status_code=404, detail="Complex not found")
  return item


@router.get("/complex/{complex_id}/trade-trend", response_model=list[TradeTrendPointResponse])
def complex_trend(complex_id: int, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
  trend = get_trend_by_complex(session, complex_id)
  if trend is None:
    raise HTTPException(status_code=404, detail="Complex not found")
  return trend
