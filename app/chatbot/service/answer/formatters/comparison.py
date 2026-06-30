from __future__ import annotations

from typing import Any

from .common import clean_text, dict_value, first_non_empty, format_candidate_groups, format_price, list_value
from .recommendation import format_poi, format_poi_list, format_search_results, has_search_results


def compact_comparison_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
  return [
    {
      "complexId": item.get("complexId"),
      "complexName": item.get("complexName"),
      "address": item.get("address"),
      "latestDealAmount": item.get("latestDealAmount"),
      "latestDealAmountText": item.get("latestDealAmountText") or format_price(item.get("latestDealAmount")),
      "pyeong": item.get("pyeong"),
      "pricePerPyeong": item.get("pricePerPyeong"),
      "pricePerPyeongText": item.get("pricePerPyeongText") or format_price(item.get("pricePerPyeong")),
      "unitCnt": item.get("unitCnt"),
      "builtYear": item.get("builtYear"),
      "nearestStation": item.get("nearestStation"),
      "nearestSchool": item.get("nearestSchool"),
      "nearbyLifestyle": item.get("nearbyLifestyle", []),
      "infrastructureNotes": item.get("infrastructureNotes", []),
      "redevelopmentInfo": item.get("redevelopmentInfo", []),
    }
    for item in results
  ]


def format_comparison_result(result: dict[str, Any]) -> str:
  candidate_answer = format_candidate_groups(
    list_value(result.get("candidateGroups")),
    resolved_names=[
      clean_text(name)
      for name in list_value(result.get("resolvedApartmentNames"))
      if clean_text(name)
    ],
    resolution_notes=[
      clean_text(note)
      for note in list_value(result.get("resolutionNotes"))
      if clean_text(note)
    ],
  )
  if candidate_answer:
    return candidate_answer

  results = [dict_value(item) for item in list_value(result.get("results"))]
  missing_names = [str(name) for name in list_value(result.get("missingApartmentNames")) if str(name)]
  prefix_lines = []
  if missing_names:
    prefix_lines.append(f"일부 아파트를 찾지 못했습니다: {', '.join(missing_names)}")
  if len(results) < 2:
    message = "비교할 아파트 데이터가 부족합니다. 아파트명을 2개 이상 입력해 주세요."
    if not missing_names:
      message = clean_text(result.get("message")) or message
    return "\n".join([*prefix_lines, message]) if prefix_lines else message

  lines = [*prefix_lines, "조회된 데이터 기준으로 비교하면 다음과 같습니다."]
  for item in results:
    name = clean_text(item.get("complexName")) or "이름 미상"
    price = first_non_empty([
      clean_text(item.get("latestDealAmountText")),
      format_price(item.get("latestDealAmount")),
    ])
    pyeong = item.get("pyeong")
    price_per_pyeong = first_non_empty([
      clean_text(item.get("pricePerPyeongText")),
      format_price(item.get("pricePerPyeong")),
    ])
    station = format_poi(item.get("nearestStation"))
    school = format_poi(item.get("nearestSchool"))
    lifestyle = format_poi_list(item.get("nearbyLifestyle", []))
    redevelopment = format_search_results(item.get("redevelopmentInfo", []))
    parts = []
    if price:
      parts.append(f"최근 거래가 {price}")
    if pyeong is not None:
      parts.append(f"{pyeong}평")
    if price_per_pyeong:
      parts.append(f"평당가 {price_per_pyeong}")
    if item.get("unitCnt") is not None:
      parts.append(f"{item['unitCnt']}세대")
    if item.get("builtYear") is not None:
      parts.append(f"{item['builtYear']}년 준공")
    if station:
      parts.append(f"가까운 역 {station}")
    if school:
      parts.append(f"가까운 학교 {school}")
    if lifestyle:
      parts.append(f"800m 생활편의 {lifestyle}")
    if redevelopment:
      parts.append(f"재개발/정비사업 검색결과 {redevelopment}")
    if parts:
      lines.append(f"- {name}: " + ", ".join(parts))
    else:
      lines.append(f"- {name}: 조회 결과에 포함된 비교 대상입니다.")

  if has_search_results(results):
    lines.append("학군은 평판이 아니라 가까운 교육시설 거리 기준이며, 미래 가격은 예측하지 않고 웹검색된 재개발/정비사업 공개 정보만 참고로 제시했습니다.")
  else:
    lines.append("학군은 평판이 아니라 가까운 교육시설 거리 기준이며, 생활편의는 800m 이내 DB POI 기준으로만 제시했습니다.")
  return "\n".join(lines)
