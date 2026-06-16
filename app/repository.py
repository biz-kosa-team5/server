from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from typing import Any

from .database import get_connection

DEFAULT_BOUNDS = {
  "swLat": 37.40,
  "swLng": 126.90,
  "neLat": 37.60,
  "neLng": 127.20,
}


def health() -> dict[str, str]:
  return {"status": "ok"}


def region_markers(payload: dict[str, Any]) -> list[dict[str, Any]]:
  bounds = bounds_from_payload(payload)
  rows = get_connection().execute(
    """
    SELECT id, name, center_lat, center_lng, unit_cnt_sum
    FROM regions
    WHERE center_lat BETWEEN ? AND ?
      AND center_lng BETWEEN ? AND ?
    ORDER BY name
    """,
    (bounds["swLat"], bounds["neLat"], bounds["swLng"], bounds["neLng"]),
  ).fetchall()
  return [
    {
      "id": row["id"],
      "name": row["name"],
      "lat": row["center_lat"],
      "lng": row["center_lng"],
      "unitCntSum": row["unit_cnt_sum"],
    }
    for row in rows
  ]


def complex_markers(payload: dict[str, Any]) -> list[dict[str, Any]]:
  bounds = bounds_from_payload(payload)
  rows = get_connection().execute(
    """
    SELECT c.*, latest.deal_amount AS latest_deal_amount, latest.deal_date AS latest_deal_date
    FROM complexes c
    LEFT JOIN trades latest ON latest.id = (
      SELECT t.id
      FROM trades t
      WHERE t.complex_id = c.id
      ORDER BY t.deal_date DESC, t.id DESC
      LIMIT 1
    )
    WHERE c.latitude IS NOT NULL
      AND c.longitude IS NOT NULL
      AND c.latitude BETWEEN ? AND ?
      AND c.longitude BETWEEN ? AND ?
    ORDER BY c.name
    """,
    (bounds["swLat"], bounds["neLat"], bounds["swLng"], bounds["neLng"]),
  ).fetchall()

  return [
    marker
    for row in rows
    if (marker := complex_marker(row, payload)) is not None
  ]


def search_complexes(query: str, limit: int = 20) -> list[dict[str, Any]]:
  pattern = f"%{query.strip()}%"
  if pattern == "%%":
    return []
  rows = get_connection().execute(
    """
    SELECT *
    FROM complexes
    WHERE name LIKE ? OR trade_name LIKE ? OR address LIKE ?
    ORDER BY name
    LIMIT ?
    """,
    (pattern, pattern, pattern, limit),
  ).fetchall()
  return [complex_search_result(row) for row in rows]


def search_suggestions(query: str) -> list[dict[str, Any]]:
  return [
    {
      "complexId": item["complexId"],
      "complexName": item["complexName"],
      "parcelId": item["parcelId"],
      "address": item["address"],
    }
    for item in search_complexes(query, limit=10)
  ]


def root_regions() -> list[dict[str, Any]]:
  rows = get_connection().execute(
    "SELECT id, name FROM regions WHERE parent_id IS NULL ORDER BY name"
  ).fetchall()
  return [{"id": row["id"], "name": row["name"]} for row in rows]


def region_detail(region_id: int) -> dict[str, Any] | None:
  row = get_connection().execute(
    "SELECT * FROM regions WHERE id = ?",
    (region_id,),
  ).fetchone()
  if row is None:
    return None

  children = get_connection().execute(
    "SELECT id, name FROM regions WHERE parent_id = ? ORDER BY name",
    (region_id,),
  ).fetchall()
  return {
    "id": row["id"],
    "name": row["name"],
    "latitude": row["center_lat"],
    "longitude": row["center_lng"],
    "children": [{"id": child["id"], "name": child["name"]} for child in children],
  }


def region_complexes(region_id: int, limit: int, offset: int) -> list[dict[str, Any]]:
  rows = get_connection().execute(
    """
    SELECT *
    FROM complexes
    WHERE region_id = ?
    ORDER BY name
    LIMIT ? OFFSET ?
    """,
    (region_id, clamp(limit, 1, 100), max(offset, 0)),
  ).fetchall()
  return [complex_summary(row) for row in rows]


def detail_by_parcel(parcel_id: int, complex_id: int | None = None) -> dict[str, Any] | None:
  if complex_id is None:
    row = get_connection().execute(
      "SELECT * FROM complexes WHERE parcel_id = ? ORDER BY id LIMIT 1",
      (parcel_id,),
    ).fetchone()
  else:
    row = get_connection().execute(
      "SELECT * FROM complexes WHERE parcel_id = ? AND id = ?",
      (parcel_id, complex_id),
    ).fetchone()
  return None if row is None else complex_detail(row)


def detail_by_complex(complex_id: int) -> dict[str, Any] | None:
  row = get_connection().execute(
    "SELECT * FROM complexes WHERE id = ?",
    (complex_id,),
  ).fetchone()
  return None if row is None else complex_detail(row)


def parcel_complexes(parcel_id: int) -> list[dict[str, Any]]:
  rows = get_connection().execute(
    "SELECT * FROM complexes WHERE parcel_id = ? ORDER BY name",
    (parcel_id,),
  ).fetchall()
  return [complex_summary(row) for row in rows]


def trades_by_parcel(
  parcel_id: int,
  complex_id: int | None,
  page: int,
  size: int,
) -> dict[str, Any]:
  complex_rows = complexes_for_parcel(parcel_id, complex_id)
  return trades_page(parcel_id, complex_id, [row["id"] for row in complex_rows], page, size)


def trades_by_complex(complex_id: int, page: int, size: int) -> dict[str, Any] | None:
  row = get_connection().execute(
    "SELECT parcel_id FROM complexes WHERE id = ?",
    (complex_id,),
  ).fetchone()
  if row is None:
    return None
  return trades_page(row["parcel_id"], complex_id, [complex_id], page, size)


def trend_by_parcel(parcel_id: int, complex_id: int | None) -> list[dict[str, Any]]:
  complex_rows = complexes_for_parcel(parcel_id, complex_id)
  return trend_for_complex_ids([row["id"] for row in complex_rows])


def trend_by_complex(complex_id: int) -> list[dict[str, Any]] | None:
  row = get_connection().execute("SELECT id FROM complexes WHERE id = ?", (complex_id,)).fetchone()
  if row is None:
    return None
  return trend_for_complex_ids([complex_id])


def bounds_from_payload(payload: dict[str, Any]) -> dict[str, float]:
  source = payload.get("bounds") if isinstance(payload.get("bounds"), dict) else payload
  return {
    key: float(source.get(key, fallback))
    for key, fallback in DEFAULT_BOUNDS.items()
  }


def complex_marker(row: sqlite3.Row, filters: dict[str, Any]) -> dict[str, Any] | None:
  latest_trade = latest_trade_for_complex(row["id"])
  if not matches_filters(row, latest_trade, filters):
    return None
  return {
    "parcelId": row["parcel_id"],
    "complexId": row["id"],
    "name": row["name"],
    "lat": row["latitude"],
    "lng": row["longitude"],
    "latestDealAmount": None if latest_trade is None else latest_trade["deal_amount"],
    "unitCntSum": row["unit_cnt"],
  }


def matches_filters(row: sqlite3.Row, latest_trade: sqlite3.Row | None, filters: dict[str, Any]) -> bool:
  if not number_between(row["unit_cnt"], filters.get("unitMin"), filters.get("unitMax")):
    return False

  age = age_from_use_date(row["use_date"])
  if age is not None and not number_between(age, filters.get("ageMin"), filters.get("ageMax")):
    return False

  if latest_trade is None:
    return filters.get("priceEokMin") in (None, "") and filters.get("priceEokMax") in (None, "")

  price_eok = latest_trade["deal_amount"] / 10000
  area_pyeong = latest_trade["excl_area"] / 3.3058
  return (
    number_between(price_eok, filters.get("priceEokMin"), filters.get("priceEokMax"))
    and number_between(area_pyeong, filters.get("pyeongMin"), filters.get("pyeongMax"))
  )


def latest_trade_for_complex(complex_id: int) -> sqlite3.Row | None:
  return get_connection().execute(
    """
    SELECT *
    FROM trades
    WHERE complex_id = ?
    ORDER BY deal_date DESC, id DESC
    LIMIT 1
    """,
    (complex_id,),
  ).fetchone()


def complex_search_result(row: sqlite3.Row) -> dict[str, Any]:
  return {
    "complexId": row["id"],
    "complexName": row["name"],
    "parcelId": row["parcel_id"],
    "latitude": row["latitude"],
    "longitude": row["longitude"],
    "address": row["address"],
  }


def complex_summary(row: sqlite3.Row) -> dict[str, Any]:
  return {
    "complexId": row["id"],
    "complexName": row["name"],
    "parcelId": row["parcel_id"],
    "latitude": row["latitude"],
    "longitude": row["longitude"],
    "address": row["address"],
    "dongCnt": row["dong_cnt"],
    "unitCnt": row["unit_cnt"],
    "useDate": row["use_date"],
  }


def complex_detail(row: sqlite3.Row) -> dict[str, Any]:
  return {
    "parcelId": row["parcel_id"],
    "complexId": row["id"],
    "latitude": row["latitude"],
    "longitude": row["longitude"],
    "address": row["address"],
    "tradeName": row["trade_name"],
    "name": row["name"],
    "dongCnt": row["dong_cnt"],
    "unitCnt": row["unit_cnt"],
    "platArea": None,
    "archArea": None,
    "totArea": None,
    "bcRat": None,
    "vlRat": None,
    "useDate": row["use_date"],
  }


def complexes_for_parcel(parcel_id: int, complex_id: int | None) -> list[sqlite3.Row]:
  if complex_id is None:
    return get_connection().execute(
      "SELECT id FROM complexes WHERE parcel_id = ?",
      (parcel_id,),
    ).fetchall()
  return get_connection().execute(
    "SELECT id FROM complexes WHERE parcel_id = ? AND id = ?",
    (parcel_id, complex_id),
  ).fetchall()


def trades_page(
  parcel_id: int,
  complex_id: int | None,
  complex_ids: list[int],
  page: int,
  size: int,
) -> dict[str, Any]:
  page = max(page, 0)
  size = clamp(size, 1, 100)
  if not complex_ids:
    return {
      "parcelId": parcel_id,
      "complexId": complex_id,
      "content": [],
      "page": page,
      "size": size,
      "totalElements": 0,
      "totalPages": 0,
    }

  placeholders = ",".join("?" for _ in complex_ids)
  total = get_connection().execute(
    f"SELECT COUNT(*) AS total FROM trades WHERE complex_id IN ({placeholders})",
    complex_ids,
  ).fetchone()["total"]
  rows = get_connection().execute(
    f"""
    SELECT *
    FROM trades
    WHERE complex_id IN ({placeholders})
    ORDER BY deal_date DESC, id DESC
    LIMIT ? OFFSET ?
    """,
    [*complex_ids, size, page * size],
  ).fetchall()
  return {
    "parcelId": parcel_id,
    "complexId": complex_id,
    "content": [trade_item(row) for row in rows],
    "page": page,
    "size": size,
    "totalElements": total,
    "totalPages": math.ceil(total / size) if total else 0,
  }


def trade_item(row: sqlite3.Row) -> dict[str, Any]:
  return {
    "tradeId": row["id"],
    "dealDate": row["deal_date"],
    "exclArea": row["excl_area"],
    "dealAmount": row["deal_amount"],
    "aptDong": row["apt_dong"],
    "floor": row["floor"],
  }


def trend_for_complex_ids(complex_ids: list[int]) -> list[dict[str, Any]]:
  if not complex_ids:
    return []
  placeholders = ",".join("?" for _ in complex_ids)
  rows = get_connection().execute(
    f"""
    SELECT substr(deal_date, 1, 7) AS month,
           AVG(deal_amount) AS avg_amount,
           COUNT(*) AS trade_count,
           MIN(deal_amount) AS min_amount,
           MAX(deal_amount) AS max_amount
    FROM trades
    WHERE complex_id IN ({placeholders})
    GROUP BY substr(deal_date, 1, 7)
    ORDER BY month
    """,
    complex_ids,
  ).fetchall()
  return [
    {
      "month": row["month"],
      "avgAmount": round(row["avg_amount"], 2),
      "count": row["trade_count"],
      "minAmount": row["min_amount"],
      "maxAmount": row["max_amount"],
    }
    for row in rows
  ]


def number_between(value: float | int | None, minimum: Any, maximum: Any) -> bool:
  if value is None:
    return True
  min_number = optional_float(minimum)
  max_number = optional_float(maximum)
  return (min_number is None or value >= min_number) and (max_number is None or value <= max_number)


def optional_float(value: Any) -> float | None:
  if value in (None, ""):
    return None
  return float(value)


def age_from_use_date(value: str | None) -> int | None:
  if not value:
    return None
  return 2026 - int(value[:4])


def clamp(value: int, minimum: int, maximum: int) -> int:
  return min(max(value, minimum), maximum)
