from __future__ import annotations

from typing import Any

from .common import clean_text, dict_value, first_non_empty, format_price, list_value


def compact_recommendation_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
  compacted = []
  for item in results:
    infrastructure = dict_value(item.get("infrastructure"))
    compacted.append({
      "complexId": item.get("complexId"),
      "complexName": item.get("complexName"),
      "address": item.get("address"),
      "latitude": item.get("latitude"),
      "longitude": item.get("longitude"),
      "unitCnt": item.get("unitCnt"),
      "useDate": item.get("useDate"),
      "latestDealAmount": item.get("latestDealAmount"),
      "latestDealAmountText": item.get("latestDealAmountText") or format_price(item.get("latestDealAmount")),
      "latestDealDate": item.get("latestDealDate"),
      "exclArea": item.get("exclArea"),
      "pyeong": item.get("pyeong"),
      "matchedPois": item.get("matchedPois", []),
      "distanceM": item.get("distanceM"),
      "infrastructure": {
        "nearestStation": infrastructure.get("nearestStation"),
        "nearestEducation": infrastructure.get("nearestEducation"),
        "nearestEducationByType": infrastructure.get("nearestEducationByType"),
        "educationDistanceTotalM": infrastructure.get("educationDistanceTotalM"),
        "nearbyLifestyle": infrastructure.get("nearbyLifestyle", []),
        "requestedPreferences": infrastructure.get("requestedPreferences", []),
        "notes": infrastructure.get("notes", []),
      },
      "redevelopmentInfo": item.get("redevelopmentInfo", []),
      "investmentSignals": item.get("investmentSignals", []),
    })
  return compacted


def format_recommendation_result(result: dict[str, Any]) -> str:
  results = [dict_value(item) for item in list_value(result.get("results"))]
  criteria = dict_value(result.get("criteria"))
  if not results:
    message = clean_text(result.get("message"))
    if criteria:
      base = message or "조건에 맞는 아파트를 찾지 못했습니다."
      return f"{base} 가격, 지역, 역/학교 반경 같은 조건을 조금 완화해 보세요."
    return message or "추천에 사용할 조건이나 조회 결과가 부족합니다. 지역, 가격, 세대수, 학교 같은 조건을 함께 입력해 주세요."

  lines = ["조회된 데이터 기준으로는 다음 후보를 우선 검토할 수 있습니다."]
  for index, item in enumerate(results[:3], start=1):
    name = clean_text(item.get("complexName")) or "이름 미상"
    price = first_non_empty([
      clean_text(item.get("latestDealAmountText")),
      format_price(item.get("latestDealAmount")),
    ])
    infrastructure = dict_value(item.get("infrastructure"))
    station = format_poi(infrastructure.get("nearestStation"))
    education = format_poi(infrastructure.get("nearestEducation"))
    lifestyle = format_poi_list(infrastructure.get("nearbyLifestyle", []))
    redevelopment = format_search_results(item.get("redevelopmentInfo", []))
    investment = format_investment_signals(item.get("investmentSignals", []))
    reasons = []
    if price:
      reasons.append(f"최근 거래가 {price}")
    if station:
      reasons.append(f"가까운 역 {station}")
    if education:
      reasons.append(f"가까운 교육시설 {education}")
    if lifestyle:
      reasons.append(f"800m 생활편의 {lifestyle}")
    if not station and not education and not lifestyle:
      reasons.append("주변 인프라는 좌표/POI 데이터로 확인되지 않음")
    if redevelopment:
      reasons.append(f"재개발/정비사업 검색결과 {redevelopment}")
    if investment:
      reasons.append(f"투자 참고 신호 {investment}")
    if item.get("unitCnt") is not None:
      reasons.append(f"{item['unitCnt']}세대")
    if item.get("useDate"):
      reasons.append(f"사용승인일 {item['useDate']}")
    if reasons:
      lines.append(f"{index}. {name}: " + ", ".join(reasons))
    else:
      lines.append(f"{index}. {name}: 조회 결과에 포함된 후보입니다.")

  if has_investment_signals(results):
    lines.append("투자가치는 예측하지 않고 역세권, 준공연도, 공개 검색 결과 같은 확인 가능한 참고 신호만 제시했습니다.")
  elif has_search_results(results):
    lines.append("학군은 평판이 아니라 가까운 교육시설 거리 기준이며, 미래 가격은 예측하지 않고 웹검색된 재개발/정비사업 공개 정보만 참고로 제시했습니다.")
  else:
    lines.append("생활편의는 800m 이내 DB POI 기준이며, 현재 응답 데이터에서 확인된 재개발/정비사업 정보는 없습니다.")
  return "\n".join(lines)


def format_poi(value: Any) -> str | None:
  if not isinstance(value, dict):
    return None
  name = clean_text(value.get("name"))
  distance = value.get("distanceM")
  if not name or distance is None:
    return None
  try:
    distance_text = str(round(float(distance)))
  except (TypeError, ValueError):
    distance_text = str(distance)
  return f"{name}({distance_text}m)"


def format_poi_list(values: Any) -> str | None:
  if not isinstance(values, list) or not values:
    return None
  formatted = [format_lifestyle_poi(value) for value in values[:4]]
  formatted = [value for value in formatted if value]
  return ", ".join(formatted) if formatted else None


def format_lifestyle_poi(value: Any) -> str | None:
  if not isinstance(value, dict):
    return None
  name = clean_text(value.get("name"))
  distance = value.get("distanceM")
  subtype = clean_text(value.get("subtype"))
  if not name or distance is None:
    return None
  try:
    distance_text = str(round(float(distance)))
  except (TypeError, ValueError):
    distance_text = str(distance)
  label = f"{name}({distance_text}m"
  if subtype:
    label += f", {subtype}"
  return f"{label})"


def format_search_results(values: Any) -> str | None:
  if not isinstance(values, list) or not values:
    return None
  titles = [
    clean_text(value.get("title"))
    for value in values[:2]
    if isinstance(value, dict) and clean_text(value.get("title"))
  ]
  return " / ".join(titles) if titles else None


def format_investment_signals(values: Any) -> str | None:
  if not isinstance(values, list) or not values:
    return None
  formatted = []
  for value in values[:3]:
    if not isinstance(value, dict):
      continue
    label = clean_text(value.get("label"))
    detail = clean_text(value.get("detail"))
    if label and detail:
      formatted.append(f"{label}({detail})")
    elif label:
      formatted.append(label)
  return ", ".join(formatted) if formatted else None


def has_search_results(results: list[dict[str, Any]]) -> bool:
  return any(item.get("redevelopmentInfo") for item in results)


def has_investment_signals(results: list[dict[str, Any]]) -> bool:
  return any(item.get("investmentSignals") for item in results)
