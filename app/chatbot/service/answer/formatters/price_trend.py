"""
시세 추이 tool JSON을 읽기 쉬운 블록형 답변으로 변환합니다.
최종 답변 LLM이 수치 해석을 과하게 덧붙이지 않도록 observation 값만 사용합니다.
"""
from __future__ import annotations

from typing import Any, Callable

from .common import (
  clean_text,
  dict_value,
  format_candidate_selection,
  format_candidates,
  format_number,
  format_percent,
  format_price,
  list_value,
)


def format_price_trend_result(result: dict[str, Any]) -> str:
  candidate_answer = format_candidate_selection(price_trend_target_name(result), list_value(result.get("candidates")))
  if candidate_answer:
    return candidate_answer

  if clean_text(result.get("reason")) == "insufficient_query":
    return clean_text(result.get("message")) or "조회할 단지명이나 지역명이 부족합니다. 지역이나 단지명을 더 구체적으로 알려주세요."

  rows = [
    dict_value(item)
    for item in (list_value(result.get("data")) or list_value(result.get("rows")))
  ]
  query_type = clean_text(result.get("query_type") or result.get("observation_type"))

  if query_type in {"price_change_ranking", "ranking"} and rows:
    return format_ranking_result(result, rows)

  if query_type in {"timeseries", "price_trend"} and rows:
    return format_timeseries_result(result, rows)

  if rows:
    return format_timeseries_result(result, rows)
  return format_failure_with_candidates(result)


def format_timeseries_result(result: dict[str, Any], rows: list[dict[str, Any]]) -> str:
  target_name = price_trend_target_name(result)
  summary = timeseries_summary(result, rows)

  title = f"{target_name} 시세추이를 조회했습니다." if target_name else "시세추이를 조회했습니다."
  lines = [title]

  period_line = format_period_line(summary)
  amount_line = format_change_line(
    "평균 거래금액",
    summary.get("first_avg_deal_amount"),
    summary.get("last_avg_deal_amount"),
    format_price,
  )
  sqm_line = format_change_line(
    "㎡당 가격",
    summary.get("first_avg_price_per_sqm"),
    summary.get("last_avg_price_per_sqm"),
    format_price_per_sqm,
  )
  count_line = format_change_line(
    "거래건수",
    summary.get("first_trade_count"),
    summary.get("last_trade_count"),
    format_trade_count,
  )
  total_line = format_labeled_metric("총 거래건수", summary.get("total_trade_count"), format_trade_count)

  detail_lines = [
    line
    for line in (period_line, amount_line, sqm_line, count_line, total_line)
    if line
  ]
  if detail_lines:
    lines.append("")
    lines.extend(detail_lines)
  return "\n".join(lines)


def format_ranking_result(result: dict[str, Any], rows: list[dict[str, Any]]) -> str:
  target_name = price_trend_target_name(result)
  title = f"{target_name} 가격 변화율 순위는 다음과 같습니다." if target_name else "가격 변화율 순위는 다음과 같습니다."
  lines = [title]
  display_limit = ranking_display_limit(result, rows)

  for index, row in enumerate(rows[:display_limit], start=1):
    name = clean_text(row.get("complex_name")) or clean_text(row.get("trade_name")) or f"{index}위"
    rank = row.get("rank") or index
    if lines[-1] != "":
      lines.append("")
    lines.append(f"{rank}) {name}")

    period = format_period_range(row.get("start_period"), row.get("end_period"))
    if period:
      lines.append(f"기간: {period}")

    change_rate = format_percent(row.get("change_rate"))
    if change_rate:
      lines.append(f"변화율: {change_rate}")

    start_price = format_price_per_sqm(row.get("start_price_per_sqm"))
    end_price = format_price_per_sqm(row.get("end_price_per_sqm"))
    if start_price and end_price:
      lines.append(f"㎡당 가격: {start_price} -> {end_price}")

    address = clean_text(row.get("address"))
    if address:
      lines.append(f"주소: {address}")

  return "\n".join(lines)


def ranking_display_limit(result: dict[str, Any], rows: list[dict[str, Any]]) -> int:
  criteria = dict_value(result.get("criteria"))
  try:
    limit = int(criteria.get("limit"))
  except (TypeError, ValueError):
    limit = 0
  if limit <= 0:
    return min(len(rows), 5)
  return min(len(rows), limit)


def timeseries_summary(result: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
  summary = dict_value(result.get("summary_metrics")) or dict_value(result.get("summary"))
  if summary:
    return summary

  first = rows[0]
  last = rows[-1]
  return {
    "first_period": first.get("period_start"),
    "last_period": last.get("period_start"),
    "first_avg_deal_amount": first.get("avg_deal_amount"),
    "last_avg_deal_amount": last.get("avg_deal_amount"),
    "first_avg_price_per_sqm": first.get("avg_price_per_sqm"),
    "last_avg_price_per_sqm": last.get("avg_price_per_sqm"),
    "first_trade_count": first.get("trade_count"),
    "last_trade_count": last.get("trade_count"),
    "total_trade_count": sum(int_value(row.get("trade_count")) for row in rows),
  }


def format_period_line(summary: dict[str, Any]) -> str:
  period = format_period_range(summary.get("first_period"), summary.get("last_period"))
  return f"기간: {period}" if period else ""


def format_period_range(start: Any, end: Any) -> str:
  start_text = clean_text(start)
  end_text = clean_text(end)
  if start_text and end_text:
    return f"{start_text} ~ {end_text}"
  return start_text or end_text


def format_change_line(label: str, first: Any, last: Any, formatter: Callable[[Any], str]) -> str:
  first_text = formatter(first)
  last_text = formatter(last)
  if not first_text or not last_text:
    return ""
  return f"{label}: {first_text} -> {last_text}"


def format_labeled_metric(label: str, value: Any, formatter: Callable[[Any], str]) -> str:
  text = formatter(value)
  if not text:
    return ""
  return f"{label}: {text}"


def format_price_per_sqm(value: Any) -> str:
  number = format_number(value)
  if not number:
    return ""
  return f"{number}만원/㎡"


def format_trade_count(value: Any) -> str:
  if value is None or value == "":
    return ""
  try:
    return f"{int(value):,}건"
  except (TypeError, ValueError):
    text = clean_text(value)
    return f"{text}건" if text and not text.endswith("건") else text


def int_value(value: Any) -> int:
  try:
    return int(value)
  except (TypeError, ValueError):
    return 0


def format_failure_with_candidates(result: dict[str, Any]) -> str:
  message = clean_text(result.get("message"))
  candidates = format_candidates(result)
  if message and candidates:
    return f"{message} {candidates}"
  return message or candidates


def price_trend_target_name(result: dict[str, Any]) -> str:
  criteria = dict_value(result.get("criteria"))
  target_name = clean_text(criteria.get("target_name"))
  if target_name:
    return target_name

  slots = dict_value(result.get("slots"))
  return clean_text(slots.get("target_name"))
