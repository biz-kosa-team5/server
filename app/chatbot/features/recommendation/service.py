from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy.orm import Session

from app.chatbot.features.web_search import search_redevelopment_context, should_search_redevelopment_context
from app.real_estate.dao import all_complexes_ordered, latest_trade_for_complex
from app.real_estate.support import clean_text, criteria_from_slots, empty_result, normalize_slots, optional_int

from .filters import (
  complex_matches_base_filters,
  latest_trade_matches,
  radius_m,
  requested_infra,
  requested_school_types,
)
from .formatting import RECOMMENDATION_RESULT_LIMIT, query_result_item, sort_query_results
from .infrastructure import enrich_infrastructure, filter_items_by_poi_distance_query, find_poi_groups


CANDIDATE_POOL_LIMIT = 20


class RecommendationService:
  """추천 기능의 전체 흐름을 담당하는 service class다."""

  def __init__(self) -> None:
    self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

  def run(self, session: Session, slots: dict[str, Any], text: str = "") -> dict[str, Any]:
    """추천 후보 조회 observation을 챗봇 tool 응답으로 만든다."""
    slots = dict(slots)
    # 재건축/투자 질문이면 일반 추천 결과에 공개 검색 기반 참고 정보를 추가로 붙인다.
    slots["_include_redevelopment_context"] = (
      should_search_redevelopment_context(text)
      or slots.get("redevelopment_interest") is True
      or bool(slots.get("investment_focus"))
    )
    return self.recommend_apartments_by_filters(session, slots)

  def recommend_apartments_by_filters(self, session: Session, slots: dict[str, Any]) -> dict[str, Any]:
    """슬롯 조건에 맞는 아파트 추천 후보를 조회한다."""
    normalized = normalize_slots(slots)
    # 1차 후보는 지역/평형/신축/세대수 같은 아파트 자체 조건으로 좁힌다.
    candidates = self._find_base_candidates(session, normalized)
    # 최근 거래가가 있어야 가격/평형/거래가 조건을 함께 판단할 수 있다.
    filtered = self._filter_by_latest_trade(session, candidates, normalized)

    # station/school/commercial/medical POI 그룹을 찾고, 이후 아파트와의 거리를 계산한다.
    poi_groups = find_poi_groups(
      session,
      clean_text(normalized.get("station_name")),
      clean_text(normalized.get("school_name")),
      clean_text(normalized.get("school_type")),
      requested_school_types(normalized),
      requested_infra(normalized),
    )
    if poi_groups is None:
      return empty_result("recommendation", "poi_not_found", "조건에 맞는 역/교육시설을 찾지 못했습니다.", normalized)

    filtered = self._filter_by_poi_groups(session, filtered, poi_groups, normalized)
    if not filtered and should_expand_default_radius(normalized, poi_groups):
      # 사용자가 반경을 직접 말하지 않은 "근처" 질문은 800m 결과가 없을 때만 한 번 확장한다.
      normalized = dict(normalized)
      normalized["radius_m"] = 1500
      expanded_items = self._filter_by_latest_trade(session, candidates, normalized)
      filtered = self._filter_by_poi_groups(session, expanded_items, poi_groups, normalized)
    results = self._build_results(session, filtered, normalized)

    response = {
      "handler": "recommendation",
      "success": bool(results),
      "criteria": criteria_from_slots(normalized),
      "results": results,
      "message": "조건에 맞는 아파트를 조회했습니다." if results else "조건에 맞는 아파트를 찾지 못했습니다.",
    }
    if normalized.get("_include_candidate_pool") is True:
      candidate_pool = self._build_candidate_pool(session, filtered, normalized)
      response["_candidatePool"] = candidate_pool
      response["success"] = bool(candidate_pool)
      if candidate_pool:
        response["message"] = "조건에 맞는 아파트를 조회했습니다."
    return response

  def _find_base_candidates(self, session: Session, slots: dict[str, Any]) -> list[Any]:
    """지역/세대수/신축 조건으로 1차 후보를 만든다."""
    return [
      complex_row
      for complex_row in all_complexes_ordered(session)
      if complex_matches_base_filters(complex_row, slots)
    ]

  def _filter_by_latest_trade(self, session: Session, candidates: list[Any], slots: dict[str, Any]) -> list[dict[str, Any]]:
    """1차 후보에 최신 거래 조건을 적용하고 응답 item 형태로 바꾼다."""
    filtered = []
    for complex_row in candidates:
      latest_trade = latest_trade_for_complex(session, complex_row.id)
      if latest_trade_matches(latest_trade, slots):
        filtered.append(query_result_item(complex_row, latest_trade))
    return filtered

  def _filter_by_poi_groups(
    self,
    session: Session,
    items: list[dict[str, Any]],
    poi_groups: list[list[Any]],
    slots: dict[str, Any],
  ) -> list[dict[str, Any]]:
    """역/학교 조건이 여러 개면 조건 그룹을 순서대로 모두 통과시킨다."""
    filtered = items
    for poi_group in poi_groups:
      filtered = filter_items_by_poi_distance_query(session, filtered, poi_group, radius_m(slots))
    return filtered

  def _build_results(self, session: Session, items: list[dict[str, Any]], slots: dict[str, Any]) -> list[dict[str, Any]]:
    """인프라 정보를 붙이고 정렬/limit을 적용해 최종 추천 결과를 만든다."""
    # 각 후보에 가까운 역/학교/생활편의시설 정보를 붙인 뒤 정렬하고 최대 5개로 제한한다.
    enriched = [enrich_infrastructure(session, item, slots) for item in items]
    requested_limit = optional_int(slots.get("limit"))
    limit = min(max(requested_limit or RECOMMENDATION_RESULT_LIMIT, 1), RECOMMENDATION_RESULT_LIMIT)
    enriched = prefer_general_recommendation_items(enriched, slots, min_count=limit)
    enriched = sort_query_results(enriched, clean_text(slots.get("sort_by")))
    limited = enriched[:limit]
    if slots.get("_include_redevelopment_context") is True:
      limited = attach_redevelopment_context(limited)
    if slots.get("investment_focus") or slots.get("redevelopment_interest") is True:
      limited = attach_investment_signals(limited)
    return limited

  def _build_candidate_pool(self, session: Session, items: list[dict[str, Any]], slots: dict[str, Any]) -> list[dict[str, Any]]:
    """hard filter를 통과한 후보를 AI가 고를 수 있도록 여러 관점으로 섞어 둔다."""
    enriched = [enrich_infrastructure(session, item, slots) for item in items]
    enriched = prefer_general_recommendation_items(enriched, slots, min_count=RECOMMENDATION_RESULT_LIMIT)
    buckets = [
      sort_query_results(enriched, clean_text(slots.get("sort_by"))),
      sort_query_results(enriched, None),
      sorted(enriched, key=lambda item: -numeric_value(item.get("unitCnt"))),
      sorted(enriched, key=lambda item: -numeric_value(item.get("pyeong"))),
      sorted(enriched, key=lambda item: str(item.get("latestDealDate") or ""), reverse=True),
      sorted(enriched, key=distance_pool_sort_key),
    ]
    pool = dedupe_candidate_pool(buckets, limit=CANDIDATE_POOL_LIMIT)
    pool = [attach_candidate_caveats(item) for item in pool]
    if slots.get("_include_redevelopment_context") is True:
      pool = attach_redevelopment_context(pool)
    if slots.get("investment_focus") or slots.get("redevelopment_interest") is True:
      pool = attach_investment_signals(pool)
    return pool


RecommendationServiceDep = Annotated[RecommendationService, Depends(RecommendationService)]


def recommend_apartments_by_filters(session: Session, slots: dict[str, Any]) -> dict[str, Any]:
  """기존 함수형 import를 깨지 않기 위한 호환 wrapper다."""
  return RecommendationService().recommend_apartments_by_filters(session, slots)


def run_recommendation(session: Session, slots: dict[str, Any], text: str = "") -> dict[str, Any]:
  """chatbot recommendation tool에서 호출하는 기존 진입점이다."""
  return RecommendationService().run(session, slots, text)


def should_expand_default_radius(slots: dict[str, Any], poi_groups: list[list[Any]]) -> bool:
  """명시 반경이 없는 '근처' 질문은 800m 결과가 없으면 한 번 더 넓게 찾는다."""
  if not poi_groups:
    return False
  if slots.get("_explicit_radius_m") is True:
    return False
  return optional_int(slots.get("radius_m")) == 800


def prefer_general_recommendation_items(
  items: list[dict[str, Any]],
  slots: dict[str, Any],
  *,
  min_count: int,
) -> list[dict[str, Any]]:
  """일반 추천에서는 초소형/소단지가 바로 최종 후보가 되지 않게 한다."""
  if allows_small_or_low_price_candidates(slots):
    return items
  preferred = [
    item
    for item in items
    if not is_default_low_priority_candidate(item)
  ]
  return preferred if len(preferred) >= min_count else items


def allows_small_or_low_price_candidates(slots: dict[str, Any]) -> bool:
  if clean_text(slots.get("sort_by")) == "price_asc":
    return True
  max_pyeong = numeric_or_none(slots.get("max_pyeong"))
  return max_pyeong is not None and max_pyeong <= 15


def is_default_low_priority_candidate(item: dict[str, Any]) -> bool:
  pyeong = numeric_or_none(item.get("pyeong"))
  if pyeong is not None and pyeong < 15:
    return True
  unit_cnt = optional_int(item.get("unitCnt"))
  return unit_cnt is None or unit_cnt < 100


def attach_redevelopment_context(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
  enriched = []
  for item in items:
    copied = dict(item)
    copied["redevelopmentInfo"] = search_redevelopment_context(
      str(item.get("complexName") or ""),
      item.get("address"),
    )
    enriched.append(copied)
  return enriched


def attach_investment_signals(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
  enriched = []
  for item in items:
    copied = dict(item)
    copied["investmentSignals"] = investment_signals(item)
    enriched.append(copied)
  return enriched


def investment_signals(item: dict[str, Any]) -> list[dict[str, Any]]:
  signals = []
  station = item.get("infrastructure", {}).get("nearestStation")
  if isinstance(station, dict) and station.get("distanceM") is not None:
    signals.append({
      "type": "transport",
      "label": "역세권",
      "detail": f"{station.get('name')} {round(float(station['distanceM']))}m",
    })

  built_year = built_year_from_use_date(item.get("useDate"))
  if built_year is not None and built_year <= 1995:
    signals.append({
      "type": "building_age",
      "label": "노후 단지",
      "detail": f"{built_year}년 준공",
    })

  redevelopment_info = item.get("redevelopmentInfo")
  if isinstance(redevelopment_info, list) and redevelopment_info:
    first = redevelopment_info[0]
    if isinstance(first, dict) and first.get("title"):
      signals.append({
        "type": "redevelopment_public_info",
        "label": "정비사업 공개 검색",
        "detail": str(first["title"]),
      })

  return signals


def built_year_from_use_date(value: Any) -> int | None:
  if not value:
    return None
  try:
    return int(str(value)[:4])
  except (TypeError, ValueError):
    return None


def dedupe_candidate_pool(buckets: list[list[dict[str, Any]]], *, limit: int) -> list[dict[str, Any]]:
  pool = []
  seen_ids: set[int] = set()
  max_bucket_length = max((len(bucket) for bucket in buckets), default=0)
  for index in range(max_bucket_length):
    for bucket in buckets:
      if index >= len(bucket):
        continue
      item = bucket[index]
      complex_id = optional_int(item.get("complexId"))
      if complex_id is None or complex_id in seen_ids:
        continue
      seen_ids.add(complex_id)
      pool.append(item)
      if len(pool) >= limit:
        return pool
  return pool


def attach_candidate_caveats(item: dict[str, Any]) -> dict[str, Any]:
  copied = dict(item)
  caveats = []
  unit_cnt = optional_int(item.get("unitCnt"))
  if unit_cnt is None:
    caveats.append("세대수 없음")
  elif unit_cnt < 100:
    caveats.append("100세대 미만")
  pyeong = numeric_or_none(item.get("pyeong"))
  if pyeong is not None and pyeong < 15:
    caveats.append("15평 미만")
  if item.get("latestDealDate") is None:
    caveats.append("거래일 없음")
  if item.get("latitude") is None or item.get("longitude") is None:
    caveats.append("좌표 없음")
  copied["_caveats"] = caveats
  return copied


def distance_pool_sort_key(item: dict[str, Any]) -> float:
  distance = numeric_value(item.get("distanceM"))
  if distance is not None:
    return distance
  infrastructure = item.get("infrastructure")
  if isinstance(infrastructure, dict):
    station = infrastructure.get("nearestStation")
    if isinstance(station, dict):
      station_distance = numeric_value(station.get("distanceM"))
      if station_distance is not None:
        return station_distance
  return float("inf")


def numeric_value(value: Any) -> float:
  try:
    return float(value)
  except (TypeError, ValueError):
    return 0.0


def numeric_or_none(value: Any) -> float | None:
  try:
    return float(value)
  except (TypeError, ValueError):
    return None
