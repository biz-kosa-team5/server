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


class RecommendationService:
  """추천 기능의 전체 흐름을 담당하는 service class다."""

  def __init__(self) -> None:
    self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

  def run(self, session: Session, slots: dict[str, Any], text: str = "") -> dict[str, Any]:
    """추천 후보 조회 observation을 챗봇 tool 응답으로 만든다."""
    slots = dict(slots)
    slots["_include_redevelopment_context"] = should_search_redevelopment_context(text)
    return self.recommend_apartments_by_filters(session, slots)

  def recommend_apartments_by_filters(self, session: Session, slots: dict[str, Any]) -> dict[str, Any]:
    """슬롯 조건에 맞는 아파트 추천 후보를 조회한다."""
    normalized = normalize_slots(slots)
    candidates = self._find_base_candidates(session, normalized)
    filtered = self._filter_by_latest_trade(session, candidates, normalized)

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
      normalized = dict(normalized)
      normalized["radius_m"] = 1500
      expanded_items = self._filter_by_latest_trade(session, candidates, normalized)
      filtered = self._filter_by_poi_groups(session, expanded_items, poi_groups, normalized)
    results = self._build_results(session, filtered, normalized)

    return {
      "handler": "recommendation",
      "success": bool(results),
      "criteria": criteria_from_slots(normalized),
      "results": results,
      "message": "조건에 맞는 아파트를 조회했습니다." if results else "조건에 맞는 아파트를 찾지 못했습니다.",
    }

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
    enriched = [enrich_infrastructure(session, item, slots) for item in items]
    enriched = sort_query_results(enriched, clean_text(slots.get("sort_by")))
    requested_limit = optional_int(slots.get("limit"))
    limit = min(max(requested_limit or RECOMMENDATION_RESULT_LIMIT, 1), RECOMMENDATION_RESULT_LIMIT)
    limited = enriched[:limit]
    if slots.get("_include_redevelopment_context") is not True:
      return limited
    return attach_redevelopment_context(limited)


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
