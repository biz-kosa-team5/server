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
  data = [
    dict_value(item)
    for item in (list_value(result.get("data")) or list_value(result.get("rows")))
  ]
  query_type = clean_text(result.get("query_type") or result.get("observation_type"))
  target_name = price_trend_target_name(result)

  if query_type in {"price_change_ranking", "ranking"} and data:
    items = []
    for item in data[:3]:
      name = clean_text(item.get("complex_name"))
      rate = format_percent(item.get("change_rate"))
      if name and rate:
        items.append(f"{name} {rate}")
    if items:
      prefix = f"{target_name} 가격 변화율 순위는 " if target_name else "가격 변화율 순위는 "
      return prefix + ", ".join(items) + "입니다."

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
      prefix = f"{target_name} 시세추이를 조회했습니다. " if target_name else "시세추이를 조회했습니다. "
      return prefix + ". ".join(parts) + "."

  if data:
    first = data[0]
    last = data[-1]
    first_period = clean_text(first.get("period_start"))
    last_period = clean_text(last.get("period_start"))
    metric_key, unit = timeseries_metric(first, last)
    first_amount = format_timeseries_value(first.get(metric_key), unit)
    last_amount = format_timeseries_value(last.get(metric_key), unit)
    if first_period and last_period and first_amount and last_amount:
      prefix = f"{target_name} 시세추이를 조회했습니다. " if target_name else "시세추이를 조회했습니다. "
      return (
        f"{prefix}{first_period} 평균 {first_amount}에서 "
        f"{last_period} 평균 {last_amount}{summary_change_particle(unit)} 확인됩니다."
      )
  return clean_text(result.get("message"))


def price_trend_target_name(result: dict[str, Any]) -> str:
  criteria = dict_value(result.get("criteria"))
  target_name = clean_text(criteria.get("target_name"))
  if target_name:
    return target_name

  slots = dict_value(result.get("slots"))
  return clean_text(slots.get("target_name"))


def timeseries_metric(first: dict[str, Any], last: dict[str, Any]) -> tuple[str, str]:
  if first.get("avg_deal_amount") is not None or last.get("avg_deal_amount") is not None:
    return "avg_deal_amount", "만원"
  return "avg_price_per_sqm", "만원/㎡"


def format_timeseries_value(value: Any, unit: str) -> str:
  if unit == "만원":
    return format_price(value)
  return format_metric_value(value, unit)


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
