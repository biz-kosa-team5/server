from __future__ import annotations

import logging
import re
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy.orm import Session

from app.chatbot.features.web_search import search_redevelopment_context, should_search_redevelopment_context
from app.models import Complex
from app.real_estate.dao import latest_trade_for_complex, pois_by_category
from app.real_estate.support import (
  clean_text,
  empty_result,
  nearest_poi_for_complex,
  normalize_slots,
  pois_within_radius_for_complex,
)

from .formatting import comparison_item, find_complex_by_name
from .metrics import DEFAULT_METRICS, infrastructure_notes, normalize_metrics, requested_infra


class ComparisonService:
  """비교 기능의 전체 흐름을 담당하는 service class다."""

  def __init__(self) -> None:
    self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

  def run(self, session: Session, slots: dict[str, Any], text: str = "") -> dict[str, Any]:
    """비교 데이터 observation을 챗봇 tool 응답으로 만든다."""
    slots = dict(slots)
    slots["_original_query"] = text
    slots["_include_redevelopment_context"] = should_search_redevelopment_context(text)
    return self.compare_apartments_by_metrics(session, slots)

  def compare_apartments_by_metrics(self, session: Session, slots: dict[str, Any]) -> dict[str, Any]:
    """아파트명 목록과 비교 항목에 맞춰 비교 결과를 만든다."""
    normalized = normalize_slots(slots)
    names = normalized.get("apartment_names")
    if not isinstance(names, list) or len(names) < 2:
      # 쉼표나 "랑"으로 못 나눈 경우, 원문에서 DB 단지명을 직접 스캔해 다시 찾는다.
      names = infer_apartment_names_from_text(session, str(normalized.get("_original_query") or ""))
      if names:
        normalized["apartment_names"] = names
    if not isinstance(names, list) or len(names) < 2:
      return empty_result("comparison", "missing_apartment_names", "비교할 아파트명을 2개 이상 입력해야 합니다.", normalized)

    infra_preferences = requested_infra(normalized)
    metrics = self._resolve_metrics(normalized, infra_preferences)
    rows, missing = self._build_rows(session, names, metrics, normalized, infra_preferences)

    return {
      "handler": "comparison",
      "success": bool(rows) and not missing,
      "criteria": {
        "apartment_names": names,
        "metrics": metrics,
        "school_type": normalized.get("school_type"),
        "school_name": normalized.get("school_name"),
        "infra_preferences": sorted(infra_preferences),
      },
      "results": rows,
      "missingApartmentNames": missing,
      "message": "아파트 비교 데이터를 조회했습니다." if rows and not missing else "일부 아파트를 찾지 못했습니다.",
    }

  def _resolve_metrics(self, slots: dict[str, Any], infra_preferences: set[str]) -> list[str]:
    """명시 metric이 없으면 기본 metric을 쓰고, 인프라 조건을 반영한다."""
    metrics = slots.get("metrics")
    if not isinstance(metrics, list) or not metrics:
      metrics = DEFAULT_METRICS
    return normalize_metrics(metrics, infra_preferences)

  def _build_rows(
    self,
    session: Session,
    names: list[Any],
    metrics: list[str],
    slots: dict[str, Any],
    infra_preferences: set[str],
  ) -> tuple[list[dict[str, Any]], list[Any]]:
    """각 아파트명을 DB row로 찾고 비교용 item으로 변환한다."""
    rows = []
    missing = []
    for name in names:
      complex_row = find_complex_by_name(session, str(name))
      if complex_row is None:
        missing.append(name)
        continue

      item = comparison_item(complex_row, latest_trade_for_complex(session, complex_row.id), metrics)
      self._attach_infrastructure(session, item, complex_row, metrics, slots)
      item["infrastructureNotes"] = infrastructure_notes(infra_preferences)
      item["redevelopmentInfo"] = (
        search_redevelopment_context(complex_row.name, complex_row.address)
        if slots.get("_include_redevelopment_context") is True
        else []
      )
      rows.append(item)
    return rows, missing

  def _attach_infrastructure(
    self,
    session: Session,
    item: dict[str, Any],
    complex_row: Any,
    metrics: list[str],
    slots: dict[str, Any],
  ) -> None:
    """metric에 필요한 경우 가까운 역/학교 정보를 item에 추가한다."""
    if "nearest_station" in metrics:
      item["nearestStation"] = nearest_poi_for_complex(
        complex_row,
        pois_by_category(session, "station"),
      )
    if "nearest_school" in metrics:
      item["nearestSchool"] = nearest_poi_for_complex(
        complex_row,
        pois_by_category(
          session,
          "education",
          subtype=clean_text(slots.get("school_type")),
          name=clean_text(slots.get("school_name")),
        ),
      )
    item["nearbyLifestyle"] = nearby_lifestyle_pois(session, complex_row)


ComparisonServiceDep = Annotated[ComparisonService, Depends(ComparisonService)]


def compare_apartments_by_metrics(session: Session, slots: dict[str, Any]) -> dict[str, Any]:
  """기존 함수형 import를 깨지 않기 위한 호환 wrapper다."""
  return ComparisonService().compare_apartments_by_metrics(session, slots)


def run_comparison(session: Session, slots: dict[str, Any], text: str = "") -> dict[str, Any]:
  """chatbot comparison tool에서 호출하는 기존 진입점이다."""
  return ComparisonService().run(session, slots, text)


def nearby_lifestyle_pois(session: Session, complex_row: Any, max_distance_m: int = 800) -> list[dict[str, Any]]:
  pois = []
  for category in ("commercial", "medical"):
    pois.extend(pois_by_category(session, category))
  return pois_within_radius_for_complex(complex_row, pois, max_distance_m)[:6]


def infer_apartment_names_from_text(session: Session, text: str, limit: int = 3) -> list[str]:
  # "다성리치빌루컴스힐더테라스"처럼 붙여 쓴 비교도 처리하기 위해
  # 공백/조사/비교 표현을 제거한 문자열에서 DB 단지명을 찾아낸다.
  query_key = normalize_name_scan_text(text)
  if not query_key:
    return []

  matches = []
  for complex_id, complex_name in session.query(Complex.id, Complex.name).all():
    name_key = normalize_name_scan_text(complex_name)
    if len(name_key) < 2:
      continue
    position = query_key.find(name_key)
    if position < 0:
      continue
    matches.append({
      "id": complex_id,
      "name": complex_name,
      "position": position,
      "length": len(name_key),
    })

  selected = select_non_overlapping_name_matches(matches)
  selected.sort(key=lambda item: int(item["position"]))
  return [str(item["name"]) for item in selected[:limit]]


def select_non_overlapping_name_matches(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
  # 짧은 이름이 긴 이름 안에 겹쳐 잡히는 문제를 막기 위해 긴 단지명을 우선 선택한다.
  selected = []
  occupied_spans: list[tuple[int, int]] = []
  seen_names = set()
  for match in sorted(matches, key=lambda item: (-int(item["length"]), int(item["position"]))):
    name = str(match["name"])
    if name in seen_names:
      continue
    start = int(match["position"])
    end = start + int(match["length"])
    if any(start < occupied_end and end > occupied_start for occupied_start, occupied_end in occupied_spans):
      continue
    selected.append(match)
    occupied_spans.append((start, end))
    seen_names.add(name)
  return selected


def normalize_name_scan_text(value: Any) -> str:
  text = clean_text(value) or ""
  text = re.sub(
    r"(비교해줘|비교해봐|비교|차이|알려줘|해줘|해봐|줘|랑|이랑|와|과|하고|,|，|/|vs|VS|\s+)",
    "",
    text,
  )
  return text.replace("펠리스", "팰리스").lower()
