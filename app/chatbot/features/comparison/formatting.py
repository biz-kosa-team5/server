from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Complex, Trade
from app.real_estate.dao import find_complex_by_name as select_complex_by_name
from app.real_estate.support import built_year_from_use_date, clean_text


PYEONG_DIVISOR = 3.3058


def find_complex_by_name(session: Session, name: str) -> Complex | None:
  """사용자가 입력한 아파트명을 정리한 뒤 DB에서 단지를 찾는다."""
  normalized = clean_text(name)
  if normalized is None:
    return None
  return select_complex_by_name(session, normalized)


def comparison_item(complex_row: Complex, latest_trade: Trade | None, metrics: list[str]) -> dict[str, Any]:
  """단지 row와 최신 거래 row를 비교 응답용 dict로 바꾼다."""
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


def format_deal_amount(value: int | float | None) -> str:
  """DB의 만원 단위 금액을 사람이 읽는 문자열로 바꾼다."""
  if value is None:
    return "정보 없음"
  if value >= 10000:
    return f"{value / 10000:.1f}억원"
  return f"{int(value):,}만원"
