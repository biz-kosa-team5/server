"""
시세 추이 tool JSON을 fallback 답변 문장으로 변환합니다.
기간, 평균/변화율/거래 건수처럼 반환된 지표만 사용하고 추세 전망은 생성하지 않습니다.
"""
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
    unit = summary_value_unit(clean_text(summary.get("primary_metric")))
    first_value = format_metric_value(summary.get("first_value"), unit)
    last_value = format_metric_value(summary.get("last_value"), unit)
    change_rate = format_percent(summary.get("change_rate"))
    trade_count = summary.get("total_trade_count")
    parts = []
    if first_period and last_period and first_value and last_value:
      parts.append(
        f"{first_period} {first_value}에서 "
        f"{last_period} {last_value}{summary_change_particle(unit)} 변했습니다"
      )
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


def summary_value_unit(primary_metric: str) -> str:
  if primary_metric == "avg_deal_amount":
    return "만원"
  if primary_metric == "avg_price_per_sqm":
    return "만원/㎡"
  return ""


def format_metric_value(value: Any, unit: str) -> str:
  number = format_number(value)
  if not number or not unit:
    return number
  return f"{number}{unit}"


def summary_change_particle(unit: str) -> str:
  if unit == "만원":
    return "으로"
  return "로"
