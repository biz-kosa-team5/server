from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import get_session
from ..models import Complex, Region, Trade
from ..real_estate import (
  clamp,
  complex_detail,
  complex_summary,
  complexes_for_parcel,
  latest_trade_for_complex,
  optional_float,
  trades_page,
  trend_for_complex_ids,
)


router = APIRouter(prefix="/api/v1", tags=["real-estate"])

DEFAULT_BOUNDS = {
  "swLat": 37.40,
  "swLng": 126.90,
  "neLat": 37.60,
  "neLng": 127.20,
}


@router.post("/map/regions")
def map_regions(
  payload: dict[str, Any] = Body(default={}),
  session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
  return region_markers(session, payload)


@router.post("/map/complexes")
def map_complexes(
  payload: dict[str, Any] = Body(default={}),
  session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
  return complex_markers(session, payload)


@router.get("/search/complexes/suggestions")
def complex_suggestions(
  q: str = Query(""),
  session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
  return search_suggestions(session, q)


@router.get("/search/complexes")
def complex_search(
  q: str = Query(""),
  session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
  return search_complexes(session, q)


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


@router.get("/complex/{complex_id}")
def get_complex_detail(complex_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
  item = detail_by_complex(session, complex_id)
  if item is None:
    raise HTTPException(status_code=404, detail="Complex not found")
  return item


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


def region_markers(session: Session, payload: dict[str, Any]) -> list[dict[str, Any]]:
  bounds = bounds_from_payload(payload)
  rows = session.scalars(
    select(Region)
    .where(Region.center_lat.between(bounds["swLat"], bounds["neLat"]))
    .where(Region.center_lng.between(bounds["swLng"], bounds["neLng"]))
    .order_by(Region.name)
  ).all()
  return [
    {
      "id": row.id,
      "name": row.name,
      "lat": row.center_lat,
      "lng": row.center_lng,
      "unitCntSum": row.unit_cnt_sum,
    }
    for row in rows
  ]


def complex_markers(session: Session, payload: dict[str, Any]) -> list[dict[str, Any]]:
  bounds = bounds_from_payload(payload)
  rows = session.scalars(
    select(Complex)
    .where(Complex.latitude.is_not(None))
    .where(Complex.longitude.is_not(None))
    .where(Complex.latitude.between(bounds["swLat"], bounds["neLat"]))
    .where(Complex.longitude.between(bounds["swLng"], bounds["neLng"]))
    .order_by(Complex.name)
  ).all()
  return [
    marker
    for row in rows
    if (marker := complex_marker(session, row, payload)) is not None
  ]


def search_complexes(session: Session, query: str, limit: int = 20) -> list[dict[str, Any]]:
  trimmed = query.strip()
  if not trimmed:
    return []
  pattern = f"%{trimmed}%"
  rows = session.scalars(
    select(Complex)
    .where(or_(Complex.name.like(pattern), Complex.trade_name.like(pattern), Complex.address.like(pattern)))
    .order_by(Complex.name)
    .limit(limit)
  ).all()
  return [complex_search_result(row) for row in rows]


def search_suggestions(session: Session, query: str) -> list[dict[str, Any]]:
  return [
    {
      "complexId": item["complexId"],
      "complexName": item["complexName"],
      "parcelId": item["parcelId"],
      "address": item["address"],
    }
    for item in search_complexes(session, query, limit=10)
  ]


def root_regions(session: Session) -> list[dict[str, Any]]:
  rows = session.scalars(
    select(Region).where(Region.parent_id.is_(None)).order_by(Region.name)
  ).all()
  return [{"id": row.id, "name": row.name} for row in rows]


def region_detail(session: Session, region_id: int) -> dict[str, Any] | None:
  row = session.get(Region, region_id)
  if row is None:
    return None

  children = session.scalars(
    select(Region).where(Region.parent_id == region_id).order_by(Region.name)
  ).all()
  return {
    "id": row.id,
    "name": row.name,
    "latitude": row.center_lat,
    "longitude": row.center_lng,
    "children": [{"id": child.id, "name": child.name} for child in children],
  }


def region_complexes(session: Session, region_id: int, limit: int, offset: int) -> list[dict[str, Any]]:
  rows = session.scalars(
    select(Complex)
    .where(Complex.region_id == region_id)
    .order_by(Complex.name)
    .limit(clamp(limit, 1, 100))
    .offset(max(offset, 0))
  ).all()
  return [complex_summary(row) for row in rows]


def detail_by_parcel(
  session: Session,
  parcel_id: int,
  complex_id: int | None = None,
) -> dict[str, Any] | None:
  statement = select(Complex).where(Complex.parcel_id == parcel_id).order_by(Complex.id).limit(1)
  if complex_id is not None:
    statement = select(Complex).where(Complex.parcel_id == parcel_id, Complex.id == complex_id)
  row = session.scalar(statement)
  return None if row is None else complex_detail(row)


def detail_by_complex(session: Session, complex_id: int) -> dict[str, Any] | None:
  row = session.get(Complex, complex_id)
  return None if row is None else complex_detail(row)


def parcel_complexes(session: Session, parcel_id: int) -> list[dict[str, Any]]:
  rows = session.scalars(
    select(Complex).where(Complex.parcel_id == parcel_id).order_by(Complex.name)
  ).all()
  return [complex_summary(row) for row in rows]


def trades_by_parcel(
  session: Session,
  parcel_id: int,
  complex_id: int | None,
  page: int,
  size: int,
) -> dict[str, Any]:
  complex_ids = complexes_for_parcel(session, parcel_id, complex_id)
  return trades_page(session, parcel_id, complex_id, complex_ids, page, size)


def trades_by_complex(session: Session, complex_id: int, page: int, size: int) -> dict[str, Any] | None:
  complex_row = session.get(Complex, complex_id)
  if complex_row is None:
    return None
  return trades_page(session, complex_row.parcel_id, complex_id, [complex_id], page, size)


def trend_by_parcel(session: Session, parcel_id: int, complex_id: int | None) -> list[dict[str, Any]]:
  complex_ids = complexes_for_parcel(session, parcel_id, complex_id)
  return trend_for_complex_ids(session, complex_ids)


def trend_by_complex(session: Session, complex_id: int) -> list[dict[str, Any]] | None:
  if session.get(Complex, complex_id) is None:
    return None
  return trend_for_complex_ids(session, [complex_id])


def bounds_from_payload(payload: dict[str, Any]) -> dict[str, float]:
  source = payload.get("bounds") if isinstance(payload.get("bounds"), dict) else payload
  return {
    key: float(source.get(key, fallback))
    for key, fallback in DEFAULT_BOUNDS.items()
  }


def complex_marker(session: Session, row: Complex, filters: dict[str, Any]) -> dict[str, Any] | None:
  latest_trade = latest_trade_for_complex(session, row.id)
  if not matches_filters(row, latest_trade, filters):
    return None
  return {
    "parcelId": row.parcel_id,
    "complexId": row.id,
    "name": row.name,
    "lat": row.latitude,
    "lng": row.longitude,
    "latestDealAmount": None if latest_trade is None else latest_trade.deal_amount,
    "unitCntSum": row.unit_cnt,
  }


def matches_filters(row: Complex, latest_trade: Trade | None, filters: dict[str, Any]) -> bool:
  if not number_between(row.unit_cnt, filters.get("unitMin"), filters.get("unitMax")):
    return False

  age = age_from_use_date(row.use_date)
  if age is not None and not number_between(age, filters.get("ageMin"), filters.get("ageMax")):
    return False

  if latest_trade is None:
    return filters.get("priceEokMin") in (None, "") and filters.get("priceEokMax") in (None, "")

  price_eok = latest_trade.deal_amount / 10000
  area_pyeong = latest_trade.excl_area / 3.3058
  return (
    number_between(price_eok, filters.get("priceEokMin"), filters.get("priceEokMax"))
    and number_between(area_pyeong, filters.get("pyeongMin"), filters.get("pyeongMax"))
  )


def complex_search_result(row: Complex) -> dict[str, Any]:
  return {
    "complexId": row.id,
    "complexName": row.name,
    "parcelId": row.parcel_id,
    "latitude": row.latitude,
    "longitude": row.longitude,
    "address": row.address,
  }


def number_between(value: float | int | None, minimum: Any, maximum: Any) -> bool:
  if value is None:
    return True
  min_number = optional_float(minimum)
  max_number = optional_float(maximum)
  return (min_number is None or value >= min_number) and (max_number is None or value <= max_number)


def age_from_use_date(value: str | None) -> int | None:
  if not value:
    return None
  return 2026 - int(value[:4])
