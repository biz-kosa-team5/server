from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Complex
from app.real_estate.dao import complexes_in_bounds, latest_trade_for_complex, regions_in_bounds
from app.real_estate.support import bounds_from_payload, matches_filters


def region_markers(session: Session, payload: dict[str, Any]) -> list[dict[str, Any]]:
  bounds = bounds_from_payload(payload)
  return [
    {
      "id": row.id,
      "name": row.name,
      "lat": row.center_lat,
      "lng": row.center_lng,
      "unitCntSum": row.unit_cnt_sum,
    }
    for row in regions_in_bounds(session, bounds)
  ]


def complex_markers(session: Session, payload: dict[str, Any]) -> list[dict[str, Any]]:
  bounds = bounds_from_payload(payload)
  return [
    marker
    for row in complexes_in_bounds(session, bounds)
    if (marker := complex_marker(session, row, payload)) is not None
  ]


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
