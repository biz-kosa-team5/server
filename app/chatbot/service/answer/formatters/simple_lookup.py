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
  format_candidate_selection,
  format_labeled_value,
  format_price,
  format_candidates,
  list_value,
)


MAX_REGION_TRADE_HISTORY_ROWS = 5


def format_simple_lookup_result(result: dict[str, Any]) -> str:
  if clean_text(result.get("reason")) == "insufficient_query":
    return clean_text(result.get("message")) or "조회할 단지명이 부족합니다. 지역이나 단지명을 더 구체적으로 알려주세요."

  data = list_value(result.get("data"))
  query_type = clean_text(result.get("query_type"))
  if data and query_type == "location":
    return format_location_result(
      result,
      dict_value(data[0]),
      candidates=list_value(result.get("candidates")),
    )
  if not data:
    return format_failure_with_candidates(result)

  if query_type == "region_trade_history":
    return format_region_trade_history_result(result, data)
  if query_type == "region_price_ranking":
    return format_region_ranking_result(result, data)
  if query_type in {"trade", "trade_history", "complex_price_record"}:
    return format_trade_result(result, data)
  if query_type == "region_trade_history":
    return format_region_trade_result(result, data)
  return clean_text(result.get("message"))


def format_failure_with_candidates(result: dict[str, Any]) -> str:
  candidate_answer = format_candidate_selection(criteria_name(result), list_value(result.get("candidates")))
  if candidate_answer:
    return candidate_answer

  message = clean_text(result.get("message"))
  candidates = format_candidates(result)
  if message and candidates:
    return f"{message} {candidates}"
  return message or candidates


def format_location_result(
  result: dict[str, Any],
  item: dict[str, Any],
  *,
  candidates: list[Any] | None = None,
) -> str:
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
    parts.append(f"{name} 위치는 {address}입니다.\n")
  elif address:
    parts.append(f"조회한 단지 위치는 {address}입니다.")
  elif name:
    parts.append(f"{name} 위치 정보를 조회했습니다.")
  if latitude is not None and longitude is not None:
    parts.append("지도에 표시했습니다.")
  location_answer = " ".join(parts) or clean_text(result.get("message"))
  candidate_answer = format_candidate_selection(
    criteria_name(result),
    candidates or [],
    intro="같은 이름으로 확인되는 후보는 다음과 같습니다.",
  )
  return "\n".join(part for part in (location_answer, candidate_answer) if part)


def format_trade_result(result: dict[str, Any], data: list[Any]) -> str:
  total_count = len(data)
  rows = [dict_value(item) for item in data[:3]]
  name = first_non_empty([
    clean_text(rows[0].get("complex_name")) if rows else "",
    criteria_name(result),
  ])
  trade_summaries = [
    format_trade_block(row)
    for row in rows
  ]
  trade_summaries = [item for item in trade_summaries if item]
  if not trade_summaries:
    return clean_text(result.get("message"))
  heading = trade_result_heading(name, total_count, len(trade_summaries))
  body = "\n\n".join(
    f"{index}) {summary}"
    for index, summary in enumerate(trade_summaries, start=1)
  )
  return f"{heading}\n\n{body}\n\n제공된 데이터 기준입니다."


def trade_result_heading(name: str, total_count: int, shown_count: int) -> str:
  subject = f"{name} 거래내역" if name else "거래내역"
  if total_count > shown_count:
    return f"{subject}은 조회된 {total_count}건 중 {shown_count}건을 표시합니다."
  return f"{subject} {shown_count}건은 다음과 같습니다."


def format_region_trade_result(result: dict[str, Any], data: list[Any]) -> str:
  rows = [dict_value(item) for item in data[:3]]
  name = criteria_name(result)
  trade_summaries = [
    format_region_trade_row(row)
    for row in rows
  ]
  trade_summaries = [item for item in trade_summaries if item]
  if name and trade_summaries:
    return f"{name} 최신 실거래 내역은 " + ", ".join(trade_summaries) + "입니다."
  if trade_summaries:
    return "최신 실거래 내역은 " + ", ".join(trade_summaries) + "입니다."
  return clean_text(result.get("message"))


def format_region_trade_row(row: dict[str, Any]) -> str:
  complex_name = clean_text(row.get("complex_name"))
  summary = format_trade_row(row)
  if complex_name and summary:
    return f"{complex_name} {summary}"
  return summary


def format_trade_row(row: dict[str, Any]) -> str:
  date = clean_text(row.get("deal_date"))
  amount = first_non_empty([
    clean_text(row.get("deal_amount_text")),
    format_price(row.get("deal_amount")),
  ])
  area = format_labeled_value("전용", row.get("exclusive_area") or row.get("excl_area"), suffix="㎡")
  area = prefer_area_text(area, row.get("excl_area_text"))
  floor = format_floor(row.get("floor"))
  details = compact_parts([amount, area, floor])
  if date and details:
    return f"{date} " + " ".join(details)
  if details:
    return " ".join(details)
  return date


def format_trade_block(row: dict[str, Any]) -> str:
  date = clean_text(row.get("deal_date"))
  amount = first_non_empty([
    clean_text(row.get("deal_amount_text")),
    format_price(row.get("deal_amount")),
  ])
  area = format_labeled_value("전용면적:", row.get("exclusive_area") or row.get("excl_area"), suffix="㎡")
  area = prefer_area_text(area, row.get("excl_area_text"))
  price_per_m2 = first_non_empty([
    clean_text(row.get("price_per_m2_text")),
    format_price_per_m2(row.get("price_per_m2")),
  ])
  floor = format_floor(row.get("floor"))
  apt_dong = clean_text(row.get("apt_dong"))
  address = clean_text(row.get("address"))
  details = compact_parts([
    f"거래일: {date}" if date else "",
    f"거래금액: {amount}" if amount else "",
    area,
    f"㎡당 가격: {price_per_m2}" if price_per_m2 else "",
    f"층수: {floor}" if floor else "",
    f"동: {apt_dong}" if apt_dong else "",
    f"주소: {address}" if address else "",
  ])
  return "\n".join(details)


def format_region_trade_history_result(result: dict[str, Any], data: list[Any]) -> str:
  rows = [dict_value(item) for item in data[:MAX_REGION_TRADE_HISTORY_ROWS]]
  region_name = first_non_empty([
    clean_text(rows[0].get("region_name")) if rows else "",
    criteria_name(result),
  ])
  trade_summaries = [
    row
    for row in (format_region_trade_history_row(row) for row in rows)
    if row
  ]
  if trade_summaries:
    heading = f"{region_name}의 최근 실거래가 {len(trade_summaries)}건은 다음과 같습니다." if region_name else "최근 실거래가는 다음과 같습니다."
    body = "\n\n".join(
      f"{index}) {summary}"
      for index, summary in enumerate(trade_summaries, start=1)
    )
    return f"{heading}\n\n{body}\n\n제공된 데이터 기준입니다."
  return clean_text(result.get("message"))


def format_region_trade_history_row(row: dict[str, Any]) -> str:
  name = first_non_empty([
    clean_text(row.get("complex_name")),
    clean_text(row.get("trade_name")),
  ])
  date = clean_text(row.get("deal_date"))
  amount = first_non_empty([
    clean_text(row.get("deal_amount_text")),
    format_price(row.get("deal_amount")),
  ])
  area = format_labeled_value("전용면적:", row.get("exclusive_area") or row.get("excl_area"), suffix="㎡")
  area = prefer_area_text(area, row.get("excl_area_text"))
  floor = format_floor(row.get("floor"))
  address = clean_text(row.get("address"))
  price_per_m2 = first_non_empty([
    clean_text(row.get("price_per_m2_text")),
    format_price_per_m2(row.get("price_per_m2")),
  ])
  details = compact_parts([
    f"거래일: {date}" if date else "",
    f"거래금액: {amount}" if amount else "",
    area,
    f"㎡당 가격: {price_per_m2}" if price_per_m2 else "",
    f"층수: {floor}" if floor else "",
    f"주소: {address}" if address else "",
  ])
  if name and details:
    return f"{name}\n" + "\n".join(details)
  if details:
    return "\n".join(details)
  return name


def format_region_ranking_result(result: dict[str, Any], data: list[Any]) -> str:
  rows = [dict_value(item) for item in data[:MAX_REGION_TRADE_HISTORY_ROWS]]
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
    criteria = dict_value(result.get("criteria"))
    price_order = clean_text(criteria.get("price_order"))
    metric_name = "최저가" if price_order == "lowest" else "최고가"
    heading = f"{region_name} 아파트 {metric_name} 순위는 다음과 같습니다."
    return f"{heading}\n\n" + "\n\n".join(ranking_summaries) + "\n\n제공된 데이터 기준입니다."
  if ranking_summaries:
    return "가격 순위는 다음과 같습니다.\n\n" + "\n\n".join(ranking_summaries) + "\n\n제공된 데이터 기준입니다."
  return clean_text(result.get("message"))


def format_region_ranking_row(row: dict[str, Any]) -> str:
  rank = row.get("rank")
  rank_label = f"{rank})" if rank is not None else ""
  name = first_non_empty([
    clean_text(row.get("complex_name")),
    clean_text(row.get("trade_name")),
  ])
  date = clean_text(row.get("deal_date"))
  amount = first_non_empty([
    clean_text(row.get("deal_amount_text")),
    format_price(row.get("deal_amount")),
  ])
  area = format_labeled_value("전용면적:", row.get("exclusive_area") or row.get("excl_area"), suffix="㎡")
  area = prefer_area_text(area, row.get("excl_area_text"))
  floor = format_floor(row.get("floor"))
  address = clean_text(row.get("address"))
  price_per_m2 = first_non_empty([
    clean_text(row.get("price_per_m2_text")),
    format_price_per_m2(row.get("price_per_m2")),
  ])
  details = compact_parts([
    f"거래일: {date}" if date else "",
    f"거래금액: {amount}" if amount else "",
    area,
    f"㎡당 가격: {price_per_m2}" if price_per_m2 else "",
    f"층수: {floor}" if floor else "",
    f"주소: {address}" if address else "",
  ])
  label = " ".join(compact_parts([rank_label, name]))
  if label and details:
    return f"{label}\n" + "\n".join(details)
  if details:
    return "\n".join(details)
  return label


def format_price_per_m2(value: Any) -> str:
  if value is None or value == "":
    return ""
  try:
    return f"{float(value):,.2f}만원"
  except (TypeError, ValueError):
    text = clean_text(value)
    return text


def prefer_area_text(current: str, area_text_value: Any) -> str:
  area_text = clean_text(area_text_value)
  if not area_text:
    return current
  if ":" in current:
    return f"{current.split(':', 1)[0]}: {area_text}"
  if " " in current:
    return f"{current.split(' ', 1)[0]} {area_text}"
  return area_text


def criteria_name(result: dict[str, Any]) -> str:
  criteria = result.get("criteria")
  if not isinstance(criteria, dict):
    return ""
  return first_non_empty([
    clean_text(criteria.get("complex_name")),
    clean_text(criteria.get("target_name")),
  ])
