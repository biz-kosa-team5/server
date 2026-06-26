from __future__ import annotations

from typing import Any

from .common import (
  clean_text,
  dict_value,
  format_number,
  format_percent,
  format_price,
  list_value,
)


def format_price_trend_result(result: dict[str, Any]) -> str:
  summary = dict_value(result.get("summary"))
  data = [dict_value(item) for item in list_value(result.get("data"))]
  query_type = clean_text(result.get("query_type"))

  if query_type == "price_change_ranking" and data:
    items = []
    for item in data[:3]:
      name = clean_text(item.get("complex_name"))
      rate = format_percent(item.get("change_rate"))
      if name and rate:
        items.append(f"{name} {rate}")
    if items:
      return "가격 변화율 순위는 " + ", ".join(items) + "입니다."

  if summary:
    first_period = clean_text(summary.get("first_period"))
    last_period = clean_text(summary.get("last_period"))
    first_value = format_number(summary.get("first_value"))
    last_value = format_number(summary.get("last_value"))
    change_rate = format_percent(summary.get("change_rate"))
    trade_count = summary.get("total_trade_count")
    parts = []
    if first_period and last_period and first_value and last_value:
      parts.append(f"{first_period} {first_value}에서 {last_period} {last_value}로 변했습니다")
    if change_rate:
      parts.append(f"변화율은 {change_rate}입니다")
    if trade_count is not None:
      parts.append(f"거래 건수는 {trade_count}건입니다")
    if parts:
      return "시세추이를 조회했습니다. " + ". ".join(parts) + "."

  if data:
    first = data[0]
    last = data[-1]
    first_period = clean_text(first.get("period_start"))
    last_period = clean_text(last.get("period_start"))
    first_amount = format_price(first.get("avg_deal_amount"))
    last_amount = format_price(last.get("avg_deal_amount"))
    if first_period and last_period and first_amount and last_amount:
      return f"시세추이를 조회했습니다. {first_period} 평균 {first_amount}에서 {last_period} 평균 {last_amount}로 확인됩니다."
  return clean_text(result.get("message"))
