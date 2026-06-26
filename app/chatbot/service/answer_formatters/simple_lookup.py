from __future__ import annotations

from typing import Any

from .common import (
  clean_text,
  compact_parts,
  dict_value,
  first_non_empty,
  format_floor,
  format_labeled_value,
  format_price,
  list_value,
)


def format_simple_lookup_result(result: dict[str, Any]) -> str:
  data = list_value(result.get("data"))
  if not data:
    return clean_text(result.get("message"))

  query_type = clean_text(result.get("query_type"))
  if query_type == "location":
    return format_location_result(result, dict_value(data[0]))
  if query_type == "trade":
    return format_trade_result(result, data)
  return clean_text(result.get("message"))


def format_location_result(result: dict[str, Any], item: dict[str, Any]) -> str:
  name = first_non_empty([
    clean_text(item.get("complex_name")),
    clean_text(item.get("trade_name")),
    clean_text(result.get("criteria", {}).get("complex_name")) if isinstance(result.get("criteria"), dict) else "",
  ])
  address = clean_text(item.get("address"))
  latitude = item.get("latitude")
  longitude = item.get("longitude")
  parts = []
  if name and address:
    parts.append(f"{name} 위치는 {address}입니다.")
  elif address:
    parts.append(f"조회한 단지 위치는 {address}입니다.")
  elif name:
    parts.append(f"{name} 위치 정보를 조회했습니다.")
  if latitude is not None and longitude is not None:
    parts.append(f"좌표는 위도 {latitude}, 경도 {longitude}입니다.")
  return " ".join(parts) or clean_text(result.get("message"))


def format_trade_result(result: dict[str, Any], data: list[Any]) -> str:
  rows = [dict_value(item) for item in data[:3]]
  name = first_non_empty([
    clean_text(rows[0].get("complex_name")) if rows else "",
    clean_text(result.get("criteria", {}).get("complex_name")) if isinstance(result.get("criteria"), dict) else "",
  ])
  trade_summaries = [
    format_trade_row(row)
    for row in rows
  ]
  trade_summaries = [item for item in trade_summaries if item]
  if name and trade_summaries:
    return f"{name} 실거래 내역은 " + ", ".join(trade_summaries) + "입니다."
  if trade_summaries:
    return "실거래 내역은 " + ", ".join(trade_summaries) + "입니다."
  return clean_text(result.get("message"))


def format_trade_row(row: dict[str, Any]) -> str:
  date = clean_text(row.get("deal_date"))
  amount = format_price(row.get("deal_amount"))
  area = format_labeled_value("전용", row.get("exclusive_area"), suffix="㎡")
  floor = format_floor(row.get("floor"))
  details = compact_parts([amount, area, floor])
  if date and details:
    return f"{date} " + " ".join(details)
  if details:
    return " ".join(details)
  return date
