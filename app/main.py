from __future__ import annotations

from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query

from . import repository

app = FastAPI(title="Gangnam Three-District Real Estate API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
  return repository.health()


@app.post("/api/v1/map/regions")
def map_regions(payload: dict[str, Any] = Body(default={})) -> list[dict[str, Any]]:
  return repository.region_markers(payload)


@app.post("/api/v1/map/complexes")
def map_complexes(payload: dict[str, Any] = Body(default={})) -> list[dict[str, Any]]:
  return repository.complex_markers(payload)


@app.get("/api/v1/search/complexes/suggestions")
def complex_suggestions(q: str = Query("")) -> list[dict[str, Any]]:
  return repository.search_suggestions(q)


@app.get("/api/v1/search/complexes")
def complex_search(q: str = Query("")) -> list[dict[str, Any]]:
  return repository.search_complexes(q)


@app.get("/api/v1/region")
def regions() -> list[dict[str, Any]]:
  return repository.root_regions()


@app.get("/api/v1/region/{region_id}")
def region_detail(region_id: int) -> dict[str, Any]:
  region = repository.region_detail(region_id)
  if region is None:
    raise HTTPException(status_code=404, detail="Region not found")
  return region


@app.get("/api/v1/region/{region_id}/complexes")
def region_complexes(
  region_id: int,
  limit: int = Query(20, ge=1, le=100),
  offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
  return repository.region_complexes(region_id, limit, offset)


@app.get("/api/v1/detail/{parcel_id}")
def detail(parcel_id: int, complexId: int | None = None) -> dict[str, Any]:
  item = repository.detail_by_parcel(parcel_id, complexId)
  if item is None:
    raise HTTPException(status_code=404, detail="Complex not found")
  return item


@app.get("/api/v1/detail/{parcel_id}/complexes")
def parcel_complexes(parcel_id: int) -> list[dict[str, Any]]:
  return repository.parcel_complexes(parcel_id)


@app.get("/api/v1/trade/{parcel_id}")
def parcel_trades(
  parcel_id: int,
  complexId: int | None = None,
  page: int = Query(0, ge=0),
  size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
  return repository.trades_by_parcel(parcel_id, complexId, page, size)


@app.get("/api/v1/trade/{parcel_id}/trend")
def parcel_trend(parcel_id: int, complexId: int | None = None) -> list[dict[str, Any]]:
  return repository.trend_by_parcel(parcel_id, complexId)


@app.get("/api/v1/complex/{complex_id}")
def complex_detail(complex_id: int) -> dict[str, Any]:
  item = repository.detail_by_complex(complex_id)
  if item is None:
    raise HTTPException(status_code=404, detail="Complex not found")
  return item


@app.get("/api/v1/complex/{complex_id}/trades")
def complex_trades(
  complex_id: int,
  page: int = Query(0, ge=0),
  size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
  item = repository.trades_by_complex(complex_id, page, size)
  if item is None:
    raise HTTPException(status_code=404, detail="Complex not found")
  return item


@app.get("/api/v1/complex/{complex_id}/trade-trend")
def complex_trend(complex_id: int) -> list[dict[str, Any]]:
  trend = repository.trend_by_complex(complex_id)
  if trend is None:
    raise HTTPException(status_code=404, detail="Complex not found")
  return trend
