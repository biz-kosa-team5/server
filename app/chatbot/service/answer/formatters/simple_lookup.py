"""
단순 조회 tool JSON을 위치/거래 fallback 답변 문장으로 변환합니다.
주소, 좌표, 거래일, 가격, 면적, 층처럼 조회 결과에 있는 값만 사용합니다.
"""
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
  format_candidates,
  list_value,
)


MAX_REGION_TRADE_HISTORY_ROWS = 5


def format_simple_lookup_result(result: dict[str, Any]) -> str:
  data = list_value(result.get("data"))
  if not data:
    return format_failure_with_candidates(result)

  query_type = clean_text(result.get("query_type"))
  if query_type == "location":
    return format_location_result(result, dict_value(data[0]))
  if query_type == "region_trade_history":
    return format_region_trade_history_result(result, data)
  if query_type == "region_price_ranking":
    return format_region_ranking_result(result, data)
  if query_type in {"trade", "trade_history", "complex_price_record"}:
    return format_trade_result(result, data)
  return clean_text(result.get("message"))


def format_failure_with_candidates(result: dict[str, Any]) -> str:
  message = clean_text(result.get("message"))
  candidates = format_candidates(result)
  if message and candidates:
    return f"{message} {candidates}"
  return message or candidates


def format_location_result(result: dict[str, Any], item: dict[str, Any]) -> str:
  name = first_non_empty([
    clean_text(item.get("complex_name")),
    clean_text(item.get("trade_name")),
    criteria_name(result),
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
    parts.append("지도에 표시했습니다.")
  return " ".join(parts) or clean_text(result.get("message"))


def format_trade_result(result: dict[str, Any], data: list[Any]) -> str:
  rows = [dict_value(item) for item in data[:3]]
  name = first_non_empty([
    clean_text(rows[0].get("complex_name")) if rows else "",
    criteria_name(result),
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
  area = format_labeled_value("전용", row.get("exclusive_area") or row.get("excl_area"), suffix="㎡")
  floor = format_floor(row.get("floor"))
  details = compact_parts([amount, area, floor])
  if date and details:
    return f"{date} " + " ".join(details)
  if details:
    return " ".join(details)
  return date


def format_region_trade_history_result(result: dict[str, Any], data: list[Any]) -> str:
  rows = [dict_value(item) for item in data[:MAX_REGION_TRADE_HISTORY_ROWS]]
  region_name = first_non_empty([
    clean_text(rows[0].get("region_name")) if rows else "",
    criteria_name(result),
  ])
  trade_summaries = [
    format_region_trade_history_row(row)
    for row in rows
  ]
  trade_summaries = [item for item in trade_summaries if item]
  if region_name and trade_summaries:
    return f"{region_name} 거래내역은 " + ", ".join(trade_summaries) + "입니다."
  if trade_summaries:
    return "거래내역은 " + ", ".join(trade_summaries) + "입니다."
  return clean_text(result.get("message"))


def format_region_trade_history_row(row: dict[str, Any]) -> str:
  name = first_non_empty([
    clean_text(row.get("complex_name")),
    clean_text(row.get("trade_name")),
  ])
  date = clean_text(row.get("deal_date"))
  amount = format_price(row.get("deal_amount"))
  area = format_labeled_value("전용", row.get("exclusive_area") or row.get("excl_area"), suffix="㎡")
  floor = format_floor(row.get("floor"))
  details = compact_parts([date, amount, area, floor])
  if name and details:
    return f"{name} " + " ".join(details)
  if details:
    return " ".join(details)
  return name


def format_region_ranking_result(result: dict[str, Any], data: list[Any]) -> str:
  rows = [dict_value(item) for item in data[:3]]
  region_name = first_non_empty([
    clean_text(rows[0].get("region_name")) if rows else "",
    criteria_name(result),
  ])
  ranking_summaries = [
    format_region_ranking_row(row)
    for row in rows
  ]
  ranking_summaries = [item for item in ranking_summaries if item]
  if region_name and ranking_summaries:
    return f"{region_name} 거래 순위는 " + ", ".join(ranking_summaries) + "입니다."
  if ranking_summaries:
    return "거래 순위는 " + ", ".join(ranking_summaries) + "입니다."
  return clean_text(result.get("message"))


def format_region_ranking_row(row: dict[str, Any]) -> str:
  rank = row.get("rank")
  rank_label = f"{rank}위" if rank is not None else ""
  name = first_non_empty([
    clean_text(row.get("complex_name")),
    clean_text(row.get("trade_name")),
  ])
  date = clean_text(row.get("deal_date"))
  amount = format_price(row.get("deal_amount"))
  area = format_labeled_value("전용", row.get("exclusive_area") or row.get("excl_area"), suffix="㎡")
  price_per_m2 = format_price_per_m2(row.get("price_per_m2"))
  details = compact_parts([date, amount, area, price_per_m2])
  label = " ".join(compact_parts([rank_label, name]))
  if label and details:
    return f"{label} " + " ".join(details)
  if details:
    return " ".join(details)
  return label


def format_price_per_m2(value: Any) -> str:
  if value is None or value == "":
    return ""
  try:
    return f"㎡당 {float(value):,.2f}만원"
  except (TypeError, ValueError):
    text = clean_text(value)
    return f"㎡당 {text}" if text else ""


def criteria_name(result: dict[str, Any]) -> str:
  criteria = result.get("criteria")
  if not isinstance(criteria, dict):
    return ""
  return first_non_empty([
    clean_text(criteria.get("complex_name")),
    clean_text(criteria.get("target_name")),
  ])
