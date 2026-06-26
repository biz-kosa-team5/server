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


def format_comparison_result(result: dict[str, Any]) -> str:
  answer = clean_text(result.get("answer"))
  if answer:
    return answer

  rows = [dict_value(item) for item in list_value(result.get("results"))[:3]]
  if not rows:
    return clean_text(result.get("message"))

  summaries = []
  for row in rows:
    name = clean_text(row.get("complexName"))
    if not name:
      continue
    details = compact_parts([
      row.get("latestDealAmountText") or format_price(row.get("latestDealAmount")),
      format_labeled_value("평형", row.get("pyeong"), suffix="평"),
      row.get("pricePerPyeongText"),
      format_labeled_value("세대수", row.get("unitCnt"), suffix="세대"),
      format_labeled_value("준공", row.get("builtYear"), suffix="년"),
    ])
    summaries.append(f"{name}: {', '.join(details)}" if details else name)

  if summaries:
    missing = list_value(result.get("missingApartmentNames"))
    suffix = f" 찾지 못한 단지는 {', '.join(map(str, missing))}입니다." if missing else ""
    return "조회된 비교 데이터는 " + "; ".join(summaries) + f"입니다.{suffix}"
  return clean_text(result.get("message"))
