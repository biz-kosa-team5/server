from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.chatbot.service.rag_answer import generate_rag_answer
from app.models import Complex, Trade
from app.real_estate.dao import find_complex_by_name as select_complex_by_name
from app.real_estate.dao import latest_trade_for_complex, pois_by_category
from app.real_estate.support import built_year_from_use_date, clean_text, empty_result, nearest_poi_for_complex, normalize_slots


PYEONG_DIVISOR = 3.3058
DEFAULT_METRICS = [
  "latest_price",
  "pyeong",
  "price_per_pyeong",
  "households",
  "built_year",
  "nearest_station",
  "nearest_school",
]


def run_comparison(session: Session, slots: dict[str, Any], text: str = "") -> dict[str, Any]:
  result = compare_apartments_by_metrics(session, slots)
  result["answer"] = generate_rag_answer(
    question=text,
    intent="comparison",
    criteria=result.get("criteria", {}),
    results=result.get("results", []),
    extra={"missingApartmentNames": result.get("missingApartmentNames", [])},
  )
  return result


def compare_apartments_by_metrics(session: Session, slots: dict[str, Any]) -> dict[str, Any]:
  normalized = normalize_slots(slots)
  names = normalized.get("apartment_names")
  if not isinstance(names, list) or len(names) < 2:
    return empty_result("comparison", "missing_apartment_names", "비교할 아파트명을 2개 이상 입력해야 합니다.", normalized)

  metrics = normalized.get("metrics")
  if not isinstance(metrics, list) or not metrics:
    metrics = DEFAULT_METRICS

  infra_preferences = requested_infra(normalized)
  metrics = normalize_metrics(metrics, infra_preferences)

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
      item["nearestStation"] = nearest_poi_for_complex(
        complex_row,
        pois_by_category(session, "station"),
      )
    if "nearest_school" in metrics:
      item["nearestSchool"] = nearest_poi_for_complex(
        complex_row,
        pois_by_category(
          session,
          "education",
          subtype=clean_text(normalized.get("school_type")),
          name=clean_text(normalized.get("school_name")),
        ),
      )
    item["infrastructureNotes"] = infrastructure_notes(infra_preferences)
    rows.append(item)

  return {
    "handler": "comparison",
    "success": bool(rows) and not missing,
    "criteria": {
      "apartment_names": names,
      "metrics": metrics,
      "school_type": normalized.get("school_type"),
      "school_name": normalized.get("school_name"),
      "infra_preferences": sorted(infra_preferences),
    },
    "results": rows,
    "missingApartmentNames": missing,
    "message": "아파트 비교 데이터를 조회했습니다." if rows and not missing else "일부 아파트를 찾지 못했습니다.",
  }


def find_complex_by_name(session: Session, name: str) -> Complex | None:
  normalized = clean_text(name)
  if normalized is None:
    return None
  return select_complex_by_name(session, normalized)


def comparison_item(complex_row: Complex, latest_trade: Trade | None, metrics: list[str]) -> dict[str, Any]:
  latest_deal_amount = None if latest_trade is None else latest_trade.deal_amount
  item = {
    "complexId": complex_row.id,
    "complexName": complex_row.name,
    "parcelId": complex_row.parcel_id,
  }
  if "latest_price" in metrics:
    item["latestDealAmount"] = latest_deal_amount
    item["latestDealAmountText"] = format_deal_amount(latest_deal_amount)
  if "pyeong" in metrics:
    item["pyeong"] = None if latest_trade is None else round(latest_trade.excl_area / PYEONG_DIVISOR, 2)
  if "price_per_pyeong" in metrics:
    item["pricePerPyeong"] = (
      None if latest_trade is None else round(latest_trade.deal_amount / (latest_trade.excl_area / PYEONG_DIVISOR), 2)
    )
    item["pricePerPyeongText"] = format_deal_amount(item["pricePerPyeong"])
  if "households" in metrics:
    item["unitCnt"] = complex_row.unit_cnt
  if "built_year" in metrics:
    item["builtYear"] = built_year_from_use_date(complex_row.use_date)
  return item


def normalize_metrics(metrics: list[str], infra_preferences: set[str]) -> list[str]:
  normalized = list(metrics)
  if "transport" in infra_preferences:
    normalized.append("nearest_station")
  if "education" in infra_preferences:
    normalized.append("nearest_school")
  if "commercial" in infra_preferences:
    normalized.extend(["nearest_station", "nearest_school"])
  return dedupe(normalized)


def requested_infra(slots: dict[str, Any]) -> set[str]:
  value = slots.get("infra_preferences")
  if isinstance(value, list):
    return {
      cleaned
      for item in value
      if (cleaned := clean_text(item)) is not None
    }
  if isinstance(value, str):
    cleaned = clean_text(value)
    return set() if cleaned is None else {cleaned}
  return set()


def infrastructure_notes(infra_preferences: set[str]) -> list[str]:
  if "commercial" not in infra_preferences:
    return []
  return ["상권/생활편의 POI 데이터는 현재 DB에 없어 역/교육시설 데이터만 근거로 비교합니다."]


def format_deal_amount(value: int | float | None) -> str:
  if value is None:
    return "정보 없음"
  if value >= 10000:
    return f"{value / 10000:.1f}억 원"
  return f"{int(value):,}만 원"


def dedupe(values: list[str]) -> list[str]:
  result = []
  seen = set()
  for value in values:
    if value in seen:
      continue
    result.append(value)
    seen.add(value)
  return result
