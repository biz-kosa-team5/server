from __future__ import annotations

from typing import Any

from .common import clean_text, dict_value, first_non_empty, format_price, list_value
from .recommendation import format_poi, format_poi_list


RECOMMENDATION_FAILURE_MESSAGE = "조건에 맞는 추천 후보를 찾지 못했습니다. 지역, 반경, 가격, 생활편의 조건을 조금 완화해 보세요."
INSUFFICIENT_CANDIDATES_MESSAGE = "추천 후보가 1개만 확인되어 3개 비교는 진행하지 못했습니다. 확인된 후보는 먼저 안내드릴게요."
COMPARISON_FAILURE_MESSAGE = "추천 후보는 찾았지만 비교에 필요한 단지 정보를 충분히 확보하지 못했습니다. 후보 목록은 유지하고, 비교 기준을 가격/교통/생활편의처럼 좁혀 다시 물어볼 수 있습니다."
GENERIC_SEQUENCE_SUMMARY = "종합하면 제공된 DB 기준으로는 생활편의, 가격, 단지 규모를 함께 비교해 우선순위를 정하는 것이 좋습니다."


def format_dependent_recommendation_comparison_answer(result: dict[str, Any]) -> str:
  pair = dependent_recommendation_comparison_pair(result)
  if pair is None:
    return ""

  recommendation_result, comparison_result = pair
  recommendation_answer = format_dependent_recommendation_step_answer(
    recommendation_result,
    comparison_result,
  )
  if recommendation_result.get("success") is not True:
    return recommendation_answer or RECOMMENDATION_FAILURE_MESSAGE

  comparison_answer = format_dependent_comparison_step_answer(
    comparison_result,
    recommendation_result,
  )
  summary = format_dependent_sequence_summary(
    recommendation_result,
    comparison_result,
  )
  return "\n\n".join(
    part
    for part in (recommendation_answer, comparison_answer, summary)
    if part
  )


def dependent_recommendation_comparison_pair(result: Any) -> tuple[dict[str, Any], dict[str, Any]] | None:
  if not isinstance(result, dict):
    return None

  wrappers = [
    wrapper
    for wrapper in list_value(result.get("results"))
    if isinstance(wrapper, dict)
  ]
  recommendation_wrapper = None
  comparison_wrapper = None
  for wrapper in wrappers:
    nested_result = dict_value(wrapper.get("result"))
    if (
      recommendation_wrapper is None
      and wrapper.get("agent") == "recommendation_agent"
      and nested_result.get("handler") == "recommendation"
    ):
      recommendation_wrapper = wrapper
      continue
    if (
      recommendation_wrapper is not None
      and wrapper.get("agent") == "comparison_agent"
      and wrapper.get("dependsOn") == "recommendation_agent"
      and nested_result.get("handler") == "comparison"
    ):
      comparison_wrapper = wrapper
      break

  if recommendation_wrapper is None or comparison_wrapper is None:
    return None
  return dict_value(recommendation_wrapper.get("result")), dict_value(comparison_wrapper.get("result"))


def format_dependent_recommendation_step_answer(
  recommendation_result: dict[str, Any],
  comparison_result: dict[str, Any] | None = None,
  *,
  max_candidates: int | None = None,
) -> str:
  if recommendation_result.get("success") is not True:
    return clean_text(recommendation_result.get("message")) or RECOMMENDATION_FAILURE_MESSAGE

  rows = selected_recommendation_rows(
    recommendation_result,
    comparison_result,
    max_candidates=max_candidates,
  )
  if not rows:
    return RECOMMENDATION_FAILURE_MESSAGE

  lines = [f"먼저 조건에 맞는 추천 후보 {len(rows)}개입니다."]
  lifestyle_found = False
  for index, row in enumerate(rows, start=1):
    infrastructure = dict_value(row.get("infrastructure"))
    lifestyle = format_poi_list(infrastructure.get("nearbyLifestyle", []))
    if lifestyle:
      lifestyle_found = True
    facts = [
      value
      for value in (
        clean_text(row.get("address")),
        latest_price_text(row),
        pyeong_text(row),
        f"생활편의 {lifestyle}" if lifestyle else "",
        station_text(row),
        education_text(row),
        households_text(row),
        built_year_text(row),
      )
      if value
    ]
    detail = " · ".join(facts)
    lines.append(f"{index}. {candidate_name(row) or f'추천 후보 {index}'}" + (f" - {detail}" if detail else ""))

  if not lifestyle_found:
    lines.append("생활편의시설은 제공된 POI 데이터에서 확인되지 않았습니다.")
  return "\n".join(lines)


def format_dependent_comparison_step_answer(
  comparison_result: dict[str, Any],
  recommendation_result: dict[str, Any] | None = None,
) -> str:
  if comparison_result.get("success") is not True:
    reason = clean_text(comparison_result.get("reason"))
    if reason == "insufficient_recommendation_candidates":
      return clean_text(comparison_result.get("message")) or INSUFFICIENT_CANDIDATES_MESSAGE
    if reason == "dependency_failed":
      return ""
    return clean_text(comparison_result.get("message")) or COMPARISON_FAILURE_MESSAGE

  rows = [
    dict_value(item)
    for item in list_value(comparison_result.get("results"))
    if isinstance(item, dict)
  ]
  if len(rows) < 2:
    return clean_text(comparison_result.get("message")) or COMPARISON_FAILURE_MESSAGE

  lines = [f"이어서 위 추천 후보 {len(rows)}개를 비교하면 다음과 같습니다."]
  for row in rows:
    facts = [
      value
      for value in (
        latest_price_text(row),
        pyeong_text(row),
        price_per_pyeong_text(row),
        households_text(row),
        built_year_text(row),
        direct_station_text(row),
        direct_school_text(row),
        direct_lifestyle_text(row),
      )
      if value
    ]
    detail = ", ".join(facts)
    lines.append(f"- {candidate_name(row) or '이름 미상'}" + (f": {detail}" if detail else ": 조회 결과에 포함된 비교 대상입니다."))

  lines.extend(comparison_interpretation_lines(rows))
  return "\n".join(lines)


def format_dependent_sequence_summary(
  recommendation_result: dict[str, Any],
  comparison_result: dict[str, Any],
) -> str:
  if recommendation_result.get("success") is not True:
    return ""

  rows = [
    dict_value(item)
    for item in list_value(comparison_result.get("results"))
    if isinstance(item, dict)
  ]
  if comparison_result.get("success") is not True or len(rows) < 2:
    return f"종합하면 추천 후보는 유지하되, 비교 기준을 가격/교통/생활편의처럼 좁혀 다시 확인하는 흐름이 좋습니다."

  clauses = []
  lifestyle = best_lifestyle_access(rows)
  if lifestyle:
    clauses.append(f"생활편의 접근성을 가장 중시하면 {lifestyle[0]}")
  households = max_metric(rows, "unitCnt")
  if households:
    clauses.append(f"단지 규모와 균형을 함께 보면 {households[0]}")
  lower_price = min_metric(rows, "latestDealAmount")
  if lower_price:
    clauses.append(f"가격 부담을 낮추려면 {lower_price[0]}")

  deduped_clauses = []
  seen_names = set()
  for clause in clauses:
    name = clause.rsplit(" ", 1)[-1]
    if name in seen_names:
      continue
    seen_names.add(name)
    deduped_clauses.append(clause)

  if not deduped_clauses:
    return GENERIC_SEQUENCE_SUMMARY
  return f"종합하면 {', '.join(deduped_clauses)}를 먼저 검토하는 흐름이 좋습니다."


def selected_recommendation_rows(
  recommendation_result: dict[str, Any],
  comparison_result: dict[str, Any] | None,
  *,
  max_candidates: int | None,
) -> list[dict[str, Any]]:
  rows = [
    dict_value(item)
    for item in list_value(recommendation_result.get("results"))
    if isinstance(item, dict)
  ]
  names = comparison_candidate_names(comparison_result) if comparison_result else []
  if names:
    indexed = {
      candidate_name(row): row
      for row in rows
      if candidate_name(row)
    }
    selected = [
      indexed.get(name) or {"complexName": name}
      for name in names
    ]
    return selected[:3]
  if max_candidates is not None:
    return rows[:max_candidates]
  return rows[:3]


def comparison_candidate_names(comparison_result: dict[str, Any] | None) -> list[str]:
  if not isinstance(comparison_result, dict):
    return []
  criteria = dict_value(comparison_result.get("criteria"))
  names = [
    clean_text(name)
    for name in list_value(criteria.get("apartment_names"))
    if clean_text(name)
  ]
  if names:
    return dedupe(names)
  return dedupe([
    clean_text(name)
    for name in list_value(comparison_result.get("resolvedApartmentNames"))
    if clean_text(name)
  ])


def candidate_name(row: dict[str, Any]) -> str:
  return first_non_empty([
    clean_text(row.get("complexName")),
    clean_text(row.get("name")),
    clean_text(row.get("complex_name")),
    clean_text(row.get("tradeName")),
    clean_text(row.get("trade_name")),
  ])


def latest_price_text(row: dict[str, Any]) -> str:
  price = first_non_empty([
    clean_text(row.get("latestDealAmountText")),
    clean_text(row.get("dealAmountText")),
    format_price(row.get("latestDealAmount")),
  ])
  return f"최근 거래가 {price}" if price else ""


def pyeong_text(row: dict[str, Any]) -> str:
  pyeong = row.get("pyeong")
  return f"{pyeong}평" if pyeong not in (None, "") else ""


def price_per_pyeong_text(row: dict[str, Any]) -> str:
  price = first_non_empty([
    clean_text(row.get("pricePerPyeongText")),
    format_price(row.get("pricePerPyeong")),
  ])
  return f"평당가 {price}" if price else ""


def households_text(row: dict[str, Any]) -> str:
  households = row.get("unitCnt")
  return f"{households}세대" if households not in (None, "") else ""


def built_year_text(row: dict[str, Any]) -> str:
  built_year = row.get("builtYear")
  if built_year not in (None, ""):
    return f"{built_year}년 준공"
  use_date = clean_text(row.get("useDate"))
  if len(use_date) >= 4 and use_date[:4].isdigit():
    return f"{use_date[:4]}년 준공"
  return ""


def station_text(row: dict[str, Any]) -> str:
  infrastructure = dict_value(row.get("infrastructure"))
  station = format_poi(infrastructure.get("nearestStation"))
  return f"가까운 역 {station}" if station else ""


def education_text(row: dict[str, Any]) -> str:
  infrastructure = dict_value(row.get("infrastructure"))
  education = format_poi(infrastructure.get("nearestEducation"))
  return f"가까운 교육시설 {education}" if education else ""


def direct_station_text(row: dict[str, Any]) -> str:
  station = format_poi(row.get("nearestStation"))
  return f"가까운 역 {station}" if station else ""


def direct_school_text(row: dict[str, Any]) -> str:
  school = format_poi(row.get("nearestSchool"))
  return f"가까운 학교 {school}" if school else ""


def direct_lifestyle_text(row: dict[str, Any]) -> str:
  lifestyle = format_poi_list(row.get("nearbyLifestyle", []))
  return f"800m 생활편의 {lifestyle}" if lifestyle else ""


def comparison_interpretation_lines(rows: list[dict[str, Any]]) -> list[str]:
  lines = []
  highest_price = max_metric(rows, "latestDealAmount")
  lowest_price = min_metric(rows, "latestDealAmount")
  if highest_price and lowest_price and highest_price[0] != lowest_price[0]:
    lines.append(f"가격은 {highest_price[0]}가 가장 높고 {lowest_price[0]}가 상대적으로 낮습니다.")

  households = max_metric(rows, "unitCnt")
  if households:
    lines.append(f"세대수는 {households[0]}가 가장 큽니다.")

  lifestyle = best_lifestyle_access(rows)
  if lifestyle:
    lines.append(f"생활편의 접근성은 {lifestyle[0]}가 가장 유리합니다.")
  return lines


def max_metric(rows: list[dict[str, Any]], key: str) -> tuple[str, float] | None:
  values = metric_values(rows, key)
  return max(values, key=lambda item: item[1]) if values else None


def min_metric(rows: list[dict[str, Any]], key: str) -> tuple[str, float] | None:
  values = metric_values(rows, key)
  return min(values, key=lambda item: item[1]) if values else None


def metric_values(rows: list[dict[str, Any]], key: str) -> list[tuple[str, float]]:
  values = []
  for row in rows:
    name = candidate_name(row)
    number = float_value(row.get(key))
    if name and number is not None:
      values.append((name, number))
  return values


def best_lifestyle_access(rows: list[dict[str, Any]]) -> tuple[str, float] | None:
  values = []
  for row in rows:
    name = candidate_name(row)
    distance = nearest_lifestyle_distance(row)
    if name and distance is not None:
      values.append((name, distance))
  return min(values, key=lambda item: item[1]) if values else None


def nearest_lifestyle_distance(row: dict[str, Any]) -> float | None:
  distances = [
    distance
    for item in list_value(row.get("nearbyLifestyle"))
    if isinstance(item, dict)
    if (distance := float_value(item.get("distanceM"))) is not None
  ]
  infrastructure = dict_value(row.get("infrastructure"))
  distances.extend([
    distance
    for item in list_value(infrastructure.get("nearbyLifestyle"))
    if isinstance(item, dict)
    if (distance := float_value(item.get("distanceM"))) is not None
  ])
  return min(distances) if distances else None


def float_value(value: Any) -> float | None:
  try:
    return float(value)
  except (TypeError, ValueError):
    return None


def dedupe(values: list[str]) -> list[str]:
  result = []
  seen = set()
  for value in values:
    if value in seen:
      continue
    seen.add(value)
    result.append(value)
  return result
