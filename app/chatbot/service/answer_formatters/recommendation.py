from __future__ import annotations

from typing import Any

from .common import (
  clean_text,
  compact_parts,
  dict_value,
  format_labeled_value,
  format_price,
  list_value,
)


def format_recommendation_result(result: dict[str, Any]) -> str:
  results = [dict_value(item) for item in list_value(result.get("results"))[:3]]
  if not results:
    return clean_text(result.get("message"))

  items = []
  for item in results:
    name = clean_text(item.get("complexName"))
    if not name:
      continue
    details = compact_parts([
      item.get("latestDealAmountText") or format_price(item.get("latestDealAmount")),
      format_labeled_value("주소", item.get("address")),
      format_labeled_value("세대수", item.get("unitCnt"), suffix="세대"),
      format_labeled_value("사용승인일", item.get("useDate")),
    ])
    items.append(f"{name}({', '.join(details)})" if details else name)

  if items:
    prefix = clean_text(result.get("message")) or "조건에 맞는 아파트를 조회했습니다."
    return f"{prefix} 우선 검토할 후보는 {', '.join(items)}입니다."
  return clean_text(result.get("message"))
