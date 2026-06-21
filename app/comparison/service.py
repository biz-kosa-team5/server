from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import Complex, Trade
from ..poi.service import nearest_poi_for_complex
from ..recommendation.service import clean_text, empty_result, normalize_slots
from ..real_estate import latest_trade_for_complex


PYEONG_DIVISOR = 3.3058


def compare_apartments_by_metrics(session: Session, slots: dict[str, Any]) -> dict[str, Any]:
  normalized = normalize_slots(slots)
  names = normalized.get("apartment_names")
  if not isinstance(names, list) or len(names) < 2:
    return empty_result("comparison", "missing_apartment_names", "비교할 아파트명을 2개 이상 입력해야 합니다.", normalized)

  metrics = normalized.get("metrics")
  if not isinstance(metrics, list) or not metrics:
    metrics = [
      "latest_price",
      "pyeong",
      "price_per_pyeong",
      "households",
      "built_year",
      "nearest_station",
      "nearest_school",
    ]

  # 비교는 slots에 들어온 아파트명을 DB에서 찾고, 요청된 metric만 결과에 담는다.
  rows = []
  missing = []
  for name in names:
    complex_row = find_complex_by_name(session, str(name))
    if complex_row is None:
      missing.append(name)
      continue

    latest_trade = latest_trade_for_complex(session, complex_row.id)
    item = comparison_item(complex_row, latest_trade, metrics)
    if "nearest_station" in metrics:
      item["nearestStation"] = nearest_poi_for_complex(session, complex_row, "station")
    if "nearest_school" in metrics:
      item["nearestSchool"] = nearest_poi_for_complex(
        session,
        complex_row,
        "education",
        subtype=clean_text(normalized.get("school_type")),
        name=clean_text(normalized.get("school_name")),
      )
    rows.append(item)

  return {
    "handler": "comparison",
    "success": bool(rows) and not missing,
    "criteria": {
      "apartment_names": names,
      "metrics": metrics,
      "school_type": normalized.get("school_type"),
      "school_name": normalized.get("school_name"),
    },
    "results": rows,
    "missingApartmentNames": missing,
    "message": "아파트 비교 데이터를 조회했습니다." if rows and not missing else "일부 아파트를 찾지 못했습니다.",
  }


def find_complex_by_name(session: Session, name: str) -> Complex | None:
  # 먼저 정확히 일치하는 단지를 찾고, 없으면 부분 일치 검색으로 한 번 더 찾는다.
  normalized = clean_text(name)
  if normalized is None:
    return None
  exact = session.scalar(
    select(Complex)
    .where(or_(Complex.name == normalized, Complex.trade_name == normalized))
    .order_by(Complex.id)
    .limit(1)
  )
  if exact is not None:
    return exact
  pattern = f"%{normalized}%"
  return session.scalar(
    select(Complex)
    .where(or_(Complex.name.like(pattern), Complex.trade_name.like(pattern)))
    .order_by(Complex.name)
    .limit(1)
  )


def comparison_item(complex_row: Complex, latest_trade: Trade | None, metrics: list[str]) -> dict[str, Any]:
  item = {
    "complexId": complex_row.id,
    "complexName": complex_row.name,
    "parcelId": complex_row.parcel_id,
  }
  if "latest_price" in metrics:
    item["latestDealAmount"] = None if latest_trade is None else latest_trade.deal_amount
  if "pyeong" in metrics:
    item["pyeong"] = None if latest_trade is None else round(latest_trade.excl_area / PYEONG_DIVISOR, 2)
  if "price_per_pyeong" in metrics:
    item["pricePerPyeong"] = (
      None if latest_trade is None else round(latest_trade.deal_amount / (latest_trade.excl_area / PYEONG_DIVISOR), 2)
    )
  if "households" in metrics:
    item["unitCnt"] = complex_row.unit_cnt
  if "built_year" in metrics:
    item["builtYear"] = built_year_from_use_date(complex_row.use_date)
  return item


def built_year_from_use_date(value: str | None) -> int | None:
  if not value:
    return None
  return int(value[:4])
