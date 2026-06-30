"""챗봇 응답에 붙일 지도 액션과 UI artifact payload를 만든다."""
from __future__ import annotations

import math
import re
from typing import Any, Iterable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Complex, Region


MAX_ACTIONS = 5
MAX_RECOMMENDATION_ACTIONS = 3
MAX_COMPARISON_ACTIONS = 2
MAX_RANKING_ACTIONS = 3
MAX_ARTIFACTS = 3
MAX_RECOMMENDATION_ITEMS = 3
MAX_RANKING_ITEMS = 5
MAX_TREND_POINTS = 18

COMPLEX_MAP_LEVEL = 2
REGION_MAP_LEVEL = 7

IGNORED_VISITOR_KEYS = {
  "answer",
  "execution",
  "planType",
  "selectedAgent",
  "selectedAgents",
  "deduplicatedCount",
}

ACTION_SOURCE_PRIORITY = {
  "simple_lookup.location": 1,
  "recommendation.results": 2,
  "comparison.results": 3,
  "simple_lookup.trade_history": 4,
  "simple_lookup.region_trade_history": 5,
  "simple_lookup.complex_price_record": 6,
  "price_trend.complex_timeseries": 7,
  "simple_lookup.region_price_ranking": 8,
  "price_trend.ranking": 9,
  "price_trend.region_timeseries": 10,
}

ARTIFACT_TYPE_PRIORITY = {
  "comparison_bar_chart": 1,
  "trend_line_chart": 2,
  "ranking_list": 3,
  "recommendation_list": 4,
}


def build_chatbot_ui_payload(session: Session, response_dict: dict[str, Any]) -> dict[str, Any]:
  """기존 chatbot 응답 dict에 additive로 붙일 UI payload를 생성한다."""
  domain_results = list(iter_domain_results(response_dict))
  ui_actions = build_ui_actions(session, domain_results)
  action_ids = {action["id"] for action in ui_actions}
  ui_artifacts = build_ui_artifacts(response_dict, domain_results, action_ids)
  return {
    "uiActions": ui_actions,
    "uiArtifacts": ui_artifacts,
    "uiSummary": build_ui_summary(ui_actions, ui_artifacts),
  }


def iter_domain_results(response_dict: dict[str, Any]) -> Iterable[dict[str, Any]]:
  """result/fragments/nested wrapper 안의 domain tool 결과를 중복 없이 순회한다."""
  seen_object_ids: set[int] = set()
  seen_signatures: set[str] = set()

  def visit(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
      for item in value:
        yield from visit(item)
      return
    if not isinstance(value, dict):
      return

    object_id = id(value)
    if object_id in seen_object_ids:
      return
    seen_object_ids.add(object_id)

    if is_domain_result(value):
      signature = domain_result_signature(value)
      if signature not in seen_signatures:
        seen_signatures.add(signature)
        yield value

    for key, item in value.items():
      if key in IGNORED_VISITOR_KEYS:
        continue
      if key in {"result", "results", "fragments", "dependentResults", "dependencies"}:
        yield from visit(item)

  yield from visit(response_dict.get("result"))
  yield from visit(response_dict.get("fragments"))


def is_domain_result(value: dict[str, Any]) -> bool:
  return clean_text(value.get("handler")) in {
    "simple_lookup",
    "price_trend",
    "recommendation",
    "comparison",
    "legal_contract",
  }


def domain_result_signature(result: dict[str, Any]) -> str:
  handler = clean_text(result.get("handler"))
  query_type = clean_text(result.get("query_type"))
  observation_type = clean_text(result.get("observation_type"))
  criteria = result.get("criteria")
  rows = list_value(result.get("data")) or list_value(result.get("rows")) or list_value(result.get("results"))
  first_id = ""
  if rows and isinstance(rows[0], dict):
    first_id = str(
      first_non_empty_value(rows[0], ["complex_id", "complexId", "region_name", "complex_name", "complexName"])
      or ""
    )
  return f"{handler}|{query_type}|{observation_type}|{stable_repr(criteria)}|{first_id}"


def build_ui_actions(session: Session, domain_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
  candidates: list[tuple[int, int, dict[str, Any]]] = []
  serial = 0
  for result in domain_results:
    for source, action in actions_from_domain_result(session, result):
      priority = ACTION_SOURCE_PRIORITY.get(source)
      if priority is None:
        continue
      action["source"] = source
      candidates.append((priority, serial, action))
      serial += 1

  candidates.sort(key=lambda item: (item[0], item[1]))

  actions: list[dict[str, Any]] = []
  seen_ids: set[str] = set()
  recommendation_count = 0
  comparison_count = 0
  ranking_count = 0

  for _priority, _serial, action in candidates:
    action_id = clean_text(action.get("id"))
    if not action_id or action_id in seen_ids:
      continue

    source = clean_text(action.get("source"))
    if source == "recommendation.results":
      if recommendation_count >= MAX_RECOMMENDATION_ACTIONS:
        continue
      recommendation_count += 1
    elif source == "comparison.results":
      if comparison_count >= MAX_COMPARISON_ACTIONS:
        continue
      comparison_count += 1
    elif source in {"simple_lookup.region_price_ranking", "price_trend.ranking"}:
      if ranking_count >= MAX_RANKING_ACTIONS:
        continue
      ranking_count += 1

    seen_ids.add(action_id)
    actions.append(action)
    if len(actions) >= MAX_ACTIONS:
      break

  for index, action in enumerate(actions):
    action["autoRun"] = index == 0
    action["priority"] = "primary" if index == 0 else "secondary"
  return actions


def actions_from_domain_result(session: Session, result: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
  if result.get("success") is not True:
    return

  handler = clean_text(result.get("handler"))
  if handler == "simple_lookup":
    yield from simple_lookup_actions(session, result)
    return
  if handler == "recommendation":
    yield from recommendation_actions(session, result)
    return
  if handler == "comparison":
    yield from comparison_actions(session, result)
    return
  if handler == "price_trend":
    yield from price_trend_actions(session, result)


def simple_lookup_actions(session: Session, result: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
  query_type = clean_text(result.get("query_type"))
  data = [item for item in list_value(result.get("data")) if isinstance(item, dict)]
  if not data:
    return

  if query_type == "location":
    row = data[0]
    complex_row = resolve_complex_target(
      session,
      complex_id=to_int_or_none(row.get("complex_id")),
      name=clean_text(row.get("complex_name")),
    )
    action = focus_action_from_complex(
      merge_complex_source(row, complex_row),
      "simple_lookup.location",
    )
    if action:
      yield "simple_lookup.location", action
    return

  if query_type in {"trade_history", "region_trade_history", "complex_price_record"}:
    row = data[0]
    complex_row = resolve_complex_target(
      session,
      complex_id=to_int_or_none(row.get("complex_id")),
      name=clean_text(row.get("complex_name")),
    )
    action = focus_action_from_complex(
      merge_complex_source(row, complex_row),
      f"simple_lookup.{query_type}",
    )
    if action:
      yield f"simple_lookup.{query_type}", action
    return

  if query_type == "region_price_ranking":
    for row in data[:MAX_RANKING_ACTIONS]:
      complex_row = resolve_complex_target(
        session,
        complex_id=to_int_or_none(row.get("complex_id")),
        name=clean_text(row.get("complex_name")),
      )
      action = focus_action_from_complex(
        merge_complex_source(row, complex_row),
        "simple_lookup.region_price_ranking",
      )
      if action:
        yield "simple_lookup.region_price_ranking", action


def recommendation_actions(session: Session, result: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
  rows = [item for item in list_value(result.get("results")) if isinstance(item, dict)]
  for row in rows[:MAX_RECOMMENDATION_ACTIONS]:
    complex_row = resolve_complex_target(
      session,
      complex_id=to_int_or_none(row.get("complexId")),
      name=clean_text(row.get("complexName")),
    )
    action = focus_action_from_complex(
      merge_complex_source(row, complex_row),
      "recommendation.results",
    )
    if action:
      yield "recommendation.results", action


def comparison_actions(session: Session, result: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
  rows = [item for item in list_value(result.get("results")) if isinstance(item, dict)]
  for row in rows[:MAX_COMPARISON_ACTIONS]:
    complex_row = resolve_complex_target(
      session,
      complex_id=to_int_or_none(row.get("complexId")),
      name=clean_text(row.get("complexName")),
    )
    action = focus_action_from_complex(
      merge_complex_source(row, complex_row),
      "comparison.results",
    )
    if action:
      yield "comparison.results", action


def price_trend_actions(session: Session, result: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
  observation_type = clean_text(result.get("observation_type"))
  criteria = dict_value(result.get("criteria"))
  target_type = clean_text(criteria.get("target_type"))

  if observation_type == "timeseries" and target_type == "complex":
    complex_row = resolve_complex_target(
      session,
      complex_id=to_int_or_none(criteria.get("complex_id")),
      name=clean_text(criteria.get("target_name")),
    )
    action = focus_action_from_complex(complex_row, "price_trend.complex_timeseries")
    if action:
      yield "price_trend.complex_timeseries", action
    return

  if observation_type == "timeseries" and target_type == "region":
    region_name = first_region_name(criteria)
    region_row = resolve_region_target(session, name=region_name)
    action = focus_action_from_region(region_row, "price_trend.region_timeseries")
    if action:
      yield "price_trend.region_timeseries", action
    return

  if observation_type == "ranking":
    rows = [
      item
      for item in (list_value(result.get("rows")) or list_value(result.get("data")))
      if isinstance(item, dict)
    ]
    for row in rows[:MAX_RANKING_ACTIONS]:
      complex_row = resolve_complex_target(
        session,
        complex_id=to_int_or_none(row.get("complex_id")),
        name=clean_text(row.get("complex_name")),
      )
      action = focus_action_from_complex(
        merge_complex_source(row, complex_row),
        "price_trend.ranking",
      )
      if action:
        yield "price_trend.ranking", action


def merge_complex_source(source: dict[str, Any], complex_row: Complex | None) -> dict[str, Any]:
  merged = dict(source)
  if complex_row is None:
    return merged
  merged.setdefault("complexId", complex_row.id)
  merged.setdefault("complex_id", complex_row.id)
  merged.setdefault("complexName", complex_row.name)
  merged.setdefault("complex_name", complex_row.name)
  merged.setdefault("parcelId", complex_row.parcel_id)
  merged.setdefault("parcel_id", complex_row.parcel_id)
  merged.setdefault("latitude", complex_row.latitude)
  merged.setdefault("longitude", complex_row.longitude)
  merged.setdefault("address", complex_row.address)
  return merged


def focus_action_from_complex(complex_row: Any, source: str, label: str | None = None) -> dict[str, Any] | None:
  row = object_to_mapping(complex_row)
  name = clean_text(first_non_empty_value(row, ["complexName", "complex_name", "name", "trade_name", "tradeName"]))
  complex_id = to_int_or_none(first_non_empty_value(row, ["complexId", "complex_id", "id"]))
  parcel_id = to_int_or_none(first_non_empty_value(row, ["parcelId", "parcel_id"]))
  latitude = finite_float(first_non_empty_value(row, ["latitude", "lat"]))
  longitude = finite_float(first_non_empty_value(row, ["longitude", "lng"]))
  if latitude is None or longitude is None:
    return None
  if not name:
    name = f"단지 {complex_id}" if complex_id is not None else "선택 단지"

  action_id = complex_action_id(complex_id, name)
  return {
    "id": action_id,
    "type": "focus_map",
    "label": label or f"{name} 지도 보기",
    "autoRun": False,
    "priority": "secondary",
    "source": source,
    "target": {
      "kind": "complex",
      "name": name,
      "complexId": complex_id,
      "parcelId": parcel_id,
      "latitude": latitude,
      "longitude": longitude,
      "level": COMPLEX_MAP_LEVEL,
      "openDetail": True,
    },
  }


def focus_action_from_region(region_row: Any, source: str, label: str | None = None) -> dict[str, Any] | None:
  row = object_to_mapping(region_row)
  name = clean_text(first_non_empty_value(row, ["name", "region_name", "target_name"]))
  latitude = finite_float(first_non_empty_value(row, ["center_lat", "latitude", "lat"]))
  longitude = finite_float(first_non_empty_value(row, ["center_lng", "longitude", "lng"]))
  if not name or latitude is None or longitude is None:
    return None

  return {
    "id": f"focus_map:region:{normalize_name(name)}",
    "type": "focus_map",
    "label": label or f"{name} 지도 보기",
    "autoRun": False,
    "priority": "secondary",
    "source": source,
    "target": {
      "kind": "region",
      "name": name,
      "complexId": None,
      "parcelId": None,
      "latitude": latitude,
      "longitude": longitude,
      "level": REGION_MAP_LEVEL,
      "openDetail": False,
    },
  }


def resolve_complex_target(
  session: Session,
  complex_id: int | None = None,
  name: str | None = None,
) -> Complex | None:
  if complex_id is not None:
    found = session.get(Complex, complex_id)
    if found is not None:
      return found

  normalized_name = normalize_name(name)
  if not normalized_name:
    return None

  name_expr = func.replace(func.lower(Complex.name), " ", "")
  trade_name_expr = func.replace(func.lower(func.coalesce(Complex.trade_name, "")), " ", "")
  exact = session.scalars(
    select(Complex)
    .where(or_(name_expr == normalized_name, trade_name_expr == normalized_name))
    .order_by(Complex.id.asc())
    .limit(1)
  ).first()
  if exact is not None:
    return exact

  return session.scalars(
    select(Complex)
    .where(or_(name_expr.like(f"%{normalized_name}%"), trade_name_expr.like(f"%{normalized_name}%")))
    .order_by(Complex.id.asc())
    .limit(1)
  ).first()


def resolve_region_target(session: Session, name: str | None = None) -> Region | None:
  normalized_name = normalize_name(name)
  if not normalized_name:
    return None

  name_expr = func.replace(func.lower(Region.name), " ", "")
  exact = session.scalars(
    select(Region)
    .where(name_expr == normalized_name)
    .order_by(Region.type.asc(), Region.id.asc())
    .limit(1)
  ).first()
  if exact is not None:
    return exact

  return session.scalars(
    select(Region)
    .where(name_expr.like(f"%{normalized_name}%"))
    .order_by(Region.type.asc(), Region.id.asc())
    .limit(1)
  ).first()


def build_ui_artifacts(
  response_dict: dict[str, Any],
  domain_results: list[dict[str, Any]],
  action_ids: set[str],
) -> list[dict[str, Any]]:
  question = clean_text(response_dict.get("question"))
  artifacts: list[dict[str, Any]] = []
  for result in domain_results:
    handler = clean_text(result.get("handler"))
    if result.get("success") is not True:
      continue
    if handler == "comparison":
      artifact = comparison_bar_chart_artifact(result, action_ids, question)
      if artifact:
        artifacts.append(artifact)
    elif handler == "price_trend":
      artifacts.extend(price_trend_artifacts(result, action_ids))
    elif handler == "simple_lookup":
      artifact = simple_lookup_ranking_artifact(result, action_ids)
      if artifact:
        artifacts.append(artifact)
    elif handler == "recommendation":
      artifact = recommendation_list_artifact(result, action_ids)
      if artifact:
        artifacts.append(artifact)

  artifacts.sort(key=lambda item: ARTIFACT_TYPE_PRIORITY.get(clean_text(item.get("type")), 99))
  deduped: list[dict[str, Any]] = []
  seen_ids: set[str] = set()
  for artifact in artifacts:
    artifact_id = clean_text(artifact.get("id"))
    if not artifact_id or artifact_id in seen_ids:
      continue
    seen_ids.add(artifact_id)
    deduped.append(artifact)
    if len(deduped) >= MAX_ARTIFACTS:
      break
  return deduped


def comparison_bar_chart_artifact(
  result: dict[str, Any],
  action_ids: set[str],
  question: str,
) -> dict[str, Any] | None:
  rows = [item for item in list_value(result.get("results")) if isinstance(item, dict)]
  if len(rows) < 2:
    return None

  metric_definitions = comparison_metric_definitions()
  flattened_rows = [flatten_comparison_values(row) for row in rows]
  metrics = []
  for definition in metric_definitions:
    key = definition["key"]
    if sum(1 for values in flattened_rows if finite_float(values.get(key)) is not None) >= 2:
      metrics.append(definition)
  if not metrics:
    return None

  metric_keys = {metric["key"] for metric in metrics}
  items = []
  for row, values in zip(rows, flattened_rows, strict=False):
    name = clean_text(row.get("complexName") or row.get("complex_name") or row.get("name"))
    complex_id = to_int_or_none(row.get("complexId") or row.get("complex_id"))
    action_id = complex_action_id_if_available(complex_id, name, action_ids)
    item_values = {
      key: finite_float(values.get(key))
      for key in metric_keys
      if finite_float(values.get(key)) is not None
    }
    items.append({
      "name": name or "이름 미상",
      "complexId": complex_id,
      "parcelId": to_int_or_none(row.get("parcelId") or row.get("parcel_id")),
      "actionId": action_id,
      "values": item_values,
    })

  names = [item["name"] for item in items if item.get("name")]
  return {
    "id": f"comparison_bar_chart:{':'.join(normalize_name(name) for name in names[:3])}",
    "type": "comparison_bar_chart",
    "title": "단지 비교",
    "source": "comparison.results",
    "defaultMetric": default_comparison_metric(result, question, [metric["key"] for metric in metrics]),
    "metrics": metrics,
    "items": items,
  }


def comparison_metric_definitions() -> list[dict[str, str]]:
  return [
    {
      "key": "latestDealAmount",
      "label": "최근 거래가",
      "unit": "만원",
      "direction": "higher_is_more_expensive",
    },
    {
      "key": "pricePerPyeong",
      "label": "평당가",
      "unit": "만원",
      "direction": "higher_is_more_expensive",
    },
    {
      "key": "unitCnt",
      "label": "세대수",
      "unit": "세대",
      "direction": "higher_is_larger",
    },
    {
      "key": "builtYear",
      "label": "준공연도",
      "unit": "년",
      "direction": "higher_is_newer",
    },
    {
      "key": "nearestStationDistanceM",
      "label": "역 거리",
      "unit": "m",
      "direction": "lower_is_closer",
    },
    {
      "key": "nearestSchoolDistanceM",
      "label": "학교 거리",
      "unit": "m",
      "direction": "lower_is_closer",
    },
  ]


def flatten_comparison_values(row: dict[str, Any]) -> dict[str, Any]:
  nearest_station = dict_value(row.get("nearestStation"))
  nearest_school = dict_value(row.get("nearestSchool"))
  return {
    "latestDealAmount": row.get("latestDealAmount"),
    "pricePerPyeong": row.get("pricePerPyeong"),
    "unitCnt": row.get("unitCnt"),
    "builtYear": row.get("builtYear"),
    "nearestStationDistanceM": nearest_station.get("distanceM"),
    "nearestSchoolDistanceM": nearest_school.get("distanceM"),
  }


def default_comparison_metric(result: dict[str, Any], question: str, metric_keys: list[str]) -> str:
  criteria = dict_value(result.get("criteria"))
  metric_text = " ".join(str(item) for item in list_value(criteria.get("metrics")))
  haystack = f"{question} {metric_text}".lower()
  preferences = [
    (("역", "교통", "station", "subway"), "nearestStationDistanceM"),
    (("학교", "학군", "초등", "교육", "school"), "nearestSchoolDistanceM"),
    (("세대", "규모", "household", "unit"), "unitCnt"),
    (("가격", "시세", "거래", "평당", "price", "deal"), "latestDealAmount"),
  ]
  for keywords, metric_key in preferences:
    if metric_key in metric_keys and any(keyword in haystack for keyword in keywords):
      return metric_key
  return metric_keys[0]


def price_trend_artifacts(result: dict[str, Any], action_ids: set[str]) -> list[dict[str, Any]]:
  observation_type = clean_text(result.get("observation_type"))
  if observation_type == "timeseries":
    artifact = trend_line_chart_artifact(result)
    return [artifact] if artifact else []
  if observation_type == "ranking":
    artifact = price_trend_ranking_artifact(result, action_ids)
    return [artifact] if artifact else []
  return []


def trend_line_chart_artifact(result: dict[str, Any]) -> dict[str, Any] | None:
  rows = [
    item
    for item in (list_value(result.get("rows")) or list_value(result.get("data")))
    if isinstance(item, dict)
  ]
  points = []
  unit = "만원"
  for row in rows:
    raw_value = row.get("avg_deal_amount")
    if raw_value is None:
      raw_value = row.get("avg_price_per_sqm")
      unit = "만원/㎡"
    value = finite_float(raw_value)
    period = period_label(row.get("period_start") or row.get("period"))
    if value is None or not period:
      continue
    points.append({
      "period": period,
      "value": value,
      "count": to_int_or_none(row.get("trade_count") or row.get("count")),
    })

  points.sort(key=lambda point: point["period"])
  points = points[-MAX_TREND_POINTS:]
  if len(points) < 2:
    return None

  criteria = dict_value(result.get("criteria"))
  target_name = first_region_name(criteria) or clean_text(criteria.get("target_name")) or "시세"
  target_type = clean_text(criteria.get("target_type")) or "target"
  return {
    "id": f"trend_line_chart:{target_type}:{normalize_name(target_name)}",
    "type": "trend_line_chart",
    "title": f"{target_name} 시세 흐름",
    "source": "price_trend.timeseries",
    "unit": unit,
    "points": points,
  }


def price_trend_ranking_artifact(result: dict[str, Any], action_ids: set[str]) -> dict[str, Any] | None:
  rows = [
    item
    for item in (list_value(result.get("rows")) or list_value(result.get("data")))
    if isinstance(item, dict)
  ]
  if not rows:
    return None
  criteria = dict_value(result.get("criteria"))
  target_name = first_region_name(criteria) or clean_text(criteria.get("target_name")) or "지역"
  items = []
  for index, row in enumerate(rows[:MAX_RANKING_ITEMS], start=1):
    name = clean_text(row.get("complex_name") or row.get("complexName"))
    complex_id = to_int_or_none(row.get("complex_id") or row.get("complexId"))
    action_id = complex_action_id_if_available(complex_id, name, action_ids)
    items.append({
      "rank": to_int_or_none(row.get("rank")) or index,
      "name": name or "이름 미상",
      "metricLabel": "상승률",
      "metricValue": format_percent(row.get("change_rate")),
      "actionId": action_id,
    })
  return {
    "id": f"ranking_list:price_trend:{normalize_name(target_name)}",
    "type": "ranking_list",
    "title": f"{target_name} 상승률 상위 단지",
    "source": "price_trend.ranking",
    "items": items,
  }


def simple_lookup_ranking_artifact(result: dict[str, Any], action_ids: set[str]) -> dict[str, Any] | None:
  if clean_text(result.get("query_type")) != "region_price_ranking":
    return None
  rows = [item for item in list_value(result.get("data")) if isinstance(item, dict)]
  if not rows:
    return None
  criteria = dict_value(result.get("criteria"))
  target_name = clean_text(criteria.get("target_name")) or clean_text(rows[0].get("region_name")) or "지역"
  price_order = clean_text(criteria.get("price_order"))
  metric_label = "최저 거래가" if price_order == "lowest" else "최고 거래가"
  items = []
  for index, row in enumerate(rows[:MAX_RANKING_ITEMS], start=1):
    name = clean_text(row.get("complex_name") or row.get("complexName"))
    complex_id = to_int_or_none(row.get("complex_id") or row.get("complexId"))
    action_id = complex_action_id_if_available(complex_id, name, action_ids)
    items.append({
      "rank": to_int_or_none(row.get("rank")) or index,
      "name": name or "이름 미상",
      "metricLabel": metric_label,
      "metricValue": format_price(row.get("deal_amount")),
      "actionId": action_id,
    })
  return {
    "id": f"ranking_list:simple_lookup:{normalize_name(target_name)}:{price_order or 'price'}",
    "type": "ranking_list",
    "title": f"{target_name} 가격 순위",
    "source": "simple_lookup.region_price_ranking",
    "items": items,
  }


def recommendation_list_artifact(result: dict[str, Any], action_ids: set[str]) -> dict[str, Any] | None:
  rows = [item for item in list_value(result.get("results")) if isinstance(item, dict)]
  if not rows:
    return None
  criteria = dict_value(result.get("criteria"))
  title_target = first_non_empty_value(criteria, ["district", "region", "target_name"]) or "추천"
  items = []
  for row in rows[:MAX_RECOMMENDATION_ITEMS]:
    name = clean_text(row.get("complexName") or row.get("complex_name"))
    complex_id = to_int_or_none(row.get("complexId") or row.get("complex_id"))
    action_id = complex_action_id_if_available(complex_id, name, action_ids)
    items.append({
      "name": name or "이름 미상",
      "priceText": clean_text(row.get("latestDealAmountText")) or format_price(row.get("latestDealAmount")),
      "meta": recommendation_meta(row),
      "actionId": action_id,
    })
  return {
    "id": f"recommendation_list:{normalize_name(str(title_target))}",
    "type": "recommendation_list",
    "title": "추천 후보",
    "source": "recommendation.results",
    "items": items,
  }


def recommendation_meta(row: dict[str, Any]) -> list[str]:
  infrastructure = dict_value(row.get("infrastructure"))
  values = [
    poi_meta(infrastructure.get("nearestStation")),
    poi_meta(infrastructure.get("nearestEducation")),
  ]
  unit_cnt = to_int_or_none(row.get("unitCnt"))
  if unit_cnt is not None:
    values.append(f"{unit_cnt:,}세대")
  use_date = clean_text(row.get("useDate"))
  if use_date:
    year = use_date[:4]
    values.append(f"{year}년 사용승인" if year.isdigit() else f"{use_date} 사용승인")
  return [value for value in values if value][:3]


def poi_meta(value: Any) -> str:
  poi = dict_value(value)
  name = clean_text(poi.get("name"))
  distance = finite_float(poi.get("distanceM"))
  if not name or distance is None:
    return ""
  return f"{name} {round(distance):,}m"


def build_ui_summary(ui_actions: list[dict[str, Any]], ui_artifacts: list[dict[str, Any]]) -> dict[str, Any]:
  primary_action = next((action for action in ui_actions if action.get("autoRun") is True), None)
  target = dict_value(primary_action.get("target")) if primary_action else {}
  return {
    "hasMapFocus": primary_action is not None,
    "primaryTargetName": clean_text(target.get("name")) or None,
    "primaryActionLabel": clean_text(primary_action.get("label")) if primary_action else None,
    "artifactTypes": [artifact.get("type") for artifact in ui_artifacts if clean_text(artifact.get("type"))],
  }


def complex_action_id_if_available(complex_id: int | None, name: str, action_ids: set[str]) -> str | None:
  action_id = complex_action_id(complex_id, name)
  return action_id if action_id in action_ids else None


def complex_action_id(complex_id: int | None, name: str) -> str:
  if complex_id is not None:
    return f"focus_map:complex:{complex_id}"
  return f"focus_map:complex-name:{normalize_name(name)}"


def first_region_name(criteria: dict[str, Any]) -> str:
  region_names = list_value(criteria.get("region_names"))
  if region_names:
    return clean_text(region_names[0])
  return clean_text(criteria.get("target_name"))


def object_to_mapping(value: Any) -> dict[str, Any]:
  if value is None:
    return {}
  if isinstance(value, dict):
    return value
  return {
    "id": getattr(value, "id", None),
    "name": getattr(value, "name", None),
    "trade_name": getattr(value, "trade_name", None),
    "parcel_id": getattr(value, "parcel_id", None),
    "latitude": getattr(value, "latitude", None),
    "longitude": getattr(value, "longitude", None),
    "center_lat": getattr(value, "center_lat", None),
    "center_lng": getattr(value, "center_lng", None),
    "address": getattr(value, "address", None),
  }


def first_non_empty_value(row: dict[str, Any], keys: list[str]) -> Any:
  for key in keys:
    value = row.get(key)
    if value is not None and value != "":
      return value
  return None


def dict_value(value: Any) -> dict[str, Any]:
  return value if isinstance(value, dict) else {}


def list_value(value: Any) -> list[Any]:
  return value if isinstance(value, list) else []


def clean_text(value: Any) -> str:
  return value.strip() if isinstance(value, str) else ""


def normalize_name(value: Any) -> str:
  return "".join(clean_text(value).lower().split())


def finite_float(value: Any) -> float | None:
  if value is None or value == "":
    return None
  try:
    number = float(value)
  except (TypeError, ValueError):
    return None
  if not math.isfinite(number):
    return None
  return number


def to_int_or_none(value: Any) -> int | None:
  if value is None or value == "":
    return None
  try:
    number = int(value)
  except (TypeError, ValueError):
    return None
  return number


def period_label(value: Any) -> str:
  text = clean_text(value)
  if len(text) >= 7 and re.match(r"^\d{4}-\d{2}", text):
    return text[:7]
  return text


def format_price(value: Any) -> str:
  amount = finite_float(value)
  if amount is None:
    return ""
  if amount >= 10000:
    return f"{amount / 10000:.1f}억원"
  return f"{int(amount):,}만원"


def format_percent(value: Any) -> str:
  number = finite_float(value)
  if number is None:
    return ""
  return f"{number:.1f}%"


def stable_repr(value: Any) -> str:
  if isinstance(value, dict):
    return "|".join(f"{key}:{stable_repr(value[key])}" for key in sorted(value))
  if isinstance(value, list):
    return "[" + ",".join(stable_repr(item) for item in value) + "]"
  return str(value)
