from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, Depends, FastAPI, HTTPException, Query
from sqlalchemy.orm import Session

from . import repository
from .controllers.query_controller import router as query_router
from .database import get_session, initialize_database


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
  initialize_database()
  yield


app = FastAPI(
  title="Gangnam Three-District Real Estate API",
  version="0.1.0",
  lifespan=lifespan,
)
app.include_router(query_router)


@app.get("/health")
def health() -> dict[str, str]:
  return repository.health()


@app.post("/api/v1/map/regions")
def map_regions(
  payload: dict[str, Any] = Body(default={}),
  session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
  return repository.region_markers(session, payload)


@app.post("/api/v1/map/complexes")
def map_complexes(
  payload: dict[str, Any] = Body(default={}),
  session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
  return repository.complex_markers(session, payload)


@app.get("/api/v1/search/complexes/suggestions")
def complex_suggestions(
  q: str = Query(""),
  session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
  return repository.search_suggestions(session, q)


@app.get("/api/v1/search/complexes")
def complex_search(
  q: str = Query(""),
  session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
  return repository.search_complexes(session, q)


@app.get("/api/v1/region")
def regions(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
  return repository.root_regions(session)


@app.get("/api/v1/region/{region_id}")
def region_detail(region_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
  region = repository.region_detail(session, region_id)
  if region is None:
    raise HTTPException(status_code=404, detail="Region not found")
  return region


@app.get("/api/v1/region/{region_id}/complexes")
def region_complexes(
  region_id: int,
  limit: int = Query(20, ge=1, le=100),
  offset: int = Query(0, ge=0),
  session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
  return repository.region_complexes(session, region_id, limit, offset)


@app.get("/api/v1/detail/{parcel_id}")
def detail(
  parcel_id: int,
  complexId: int | None = None,
  session: Session = Depends(get_session),
) -> dict[str, Any]:
  item = repository.detail_by_parcel(session, parcel_id, complexId)
  if item is None:
    raise HTTPException(status_code=404, detail="Complex not found")
  return item


@app.get("/api/v1/detail/{parcel_id}/complexes")
def parcel_complexes(parcel_id: int, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
  return repository.parcel_complexes(session, parcel_id)


@app.get("/api/v1/trade/{parcel_id}")
def parcel_trades(
  parcel_id: int,
  complexId: int | None = None,
  page: int = Query(0, ge=0),
  size: int = Query(20, ge=1, le=100),
  session: Session = Depends(get_session),
) -> dict[str, Any]:
  return repository.trades_by_parcel(session, parcel_id, complexId, page, size)


@app.get("/api/v1/trade/{parcel_id}/trend")
def parcel_trend(
  parcel_id: int,
  complexId: int | None = None,
  session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
  return repository.trend_by_parcel(session, parcel_id, complexId)


@app.get("/api/v1/complex/{complex_id}")
def complex_detail(complex_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
  item = repository.detail_by_complex(session, complex_id)
  if item is None:
    raise HTTPException(status_code=404, detail="Complex not found")
  return item


@app.get("/api/v1/complex/{complex_id}/trades")
def complex_trades(
  complex_id: int,
  page: int = Query(0, ge=0),
  size: int = Query(20, ge=1, le=100),
  session: Session = Depends(get_session),
) -> dict[str, Any]:
  item = repository.trades_by_complex(session, complex_id, page, size)
  if item is None:
    raise HTTPException(status_code=404, detail="Complex not found")
  return item


@app.get("/api/v1/complex/{complex_id}/trade-trend")
def complex_trend(complex_id: int, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
  trend = repository.trend_by_complex(session, complex_id)
  if trend is None:
    raise HTTPException(status_code=404, detail="Complex not found")
  return trend
