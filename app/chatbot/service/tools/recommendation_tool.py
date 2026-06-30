from __future__ import annotations

from typing import Any

from langchain.tools import tool
from sqlalchemy.orm import Session

from app.chatbot.features.recommendation.service import run_recommendation
from app.chatbot.features.recommendation.slots import (
  extract_recommendation_slots,
  looks_like_generic_station_reference,
)
from .utils import compact_none


def build_recommendation_tool(session: Session):
  @tool
  def recommend_apartments(
    query: str,
    district: str | None = None,
    neighborhood: str | None = None,
    station_name: str | None = None,
    school_type: str | None = None,
    school_types: list[str] | None = None,
    radius_m: int | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    min_households: int | None = None,
    min_pyeong: float | None = None,
    max_pyeong: float | None = None,
    is_new_build: bool | None = None,
    min_built_year: int | None = None,
    infra_preferences: list[str] | None = None,
    investment_focus: list[str] | None = None,
    redevelopment_interest: bool | None = None,
    sort_by: str | None = None,
    limit: int | None = None,
  ) -> dict[str, Any]:
    """
    지역, 가격, 역세권, 학교/학군, 신축 여부 같은 조건에 맞는 아파트 추천 질문을 처리합니다.
    "초등학교근처", "학군 좋은 곳", "초품아"처럼 짧은 질문도 추천으로 처리합니다.

    Args:
      query: 사용자가 입력한 아파트 추천 질문입니다. 예: "송파구 40억 이하 아파트 추천해줘"
      district: 추천 대상 구 이름입니다. 예: 송파구
      neighborhood: 추천 대상 동 이름입니다. 예: 잠실동
      station_name: 가까워야 하는 역 이름입니다. 예: 잠실역
      school_type: 가까워야 하는 단일 학교 유형입니다. 예: 초등학교
      school_types: 가까워야 하는 복수 학교 유형입니다.
      radius_m: 역/학교/인프라 반경입니다. 단위는 m입니다.
      min_price: 최소 매매가입니다. 단위는 만원입니다.
      max_price: 최대 매매가입니다. 단위는 만원입니다.
      min_households: 최소 세대수입니다.
      min_pyeong: 최소 평형입니다.
      max_pyeong: 최대 평형입니다.
      is_new_build: 신축/준신축 조건 여부입니다.
      min_built_year: 최소 준공연도입니다.
      infra_preferences: transport, education, commercial, medical 중 선호 인프라 목록입니다.
      investment_focus: 투자/호재/재건축 질문에서 참고할 관심 기준입니다. 예: investment, redevelopment, development
      redevelopment_interest: 재건축/재개발/정비사업 공개 정보를 참고해야 하는지 여부입니다.
      sort_by: 정렬 기준입니다. 학교/학군/초품아/초등학교 근처 질문은 school_distance_asc를 사용하세요. 예: distance_asc, price_asc, price_desc, school_distance_asc
      limit: 반환할 최대 후보 개수입니다.

    Returns:
      dict: recommendation service가 반환한 구조화된 JSON 결과입니다.
    """
    extracted_slots = extract_recommendation_slots(query)
    llm_slots = compact_none({
      "district": district,
      "neighborhood": neighborhood,
      "station_name": station_name,
      "school_type": school_type,
      "school_types": school_types,
      "radius_m": radius_m,
      "min_price": min_price,
      "max_price": max_price,
      "min_households": min_households,
      "min_pyeong": min_pyeong,
      "max_pyeong": max_pyeong,
      "is_new_build": is_new_build,
      "min_built_year": min_built_year,
      "infra_preferences": infra_preferences,
      "investment_focus": investment_focus,
      "redevelopment_interest": redevelopment_interest,
      "sort_by": sort_by,
      "limit": limit,
    })
    slots = merge_recommendation_slots(extracted_slots, llm_slots, query)
    return run_recommendation(session, slots, query)

  return recommend_apartments


def merge_recommendation_slots(regex_slots: dict[str, Any], llm_slots: dict[str, Any], query: str) -> dict[str, Any]:
  slots = dict(regex_slots)
  overrides = dict(llm_slots)
  for key in ("neighborhood", "infra_preferences", "radius_m", "sort_by"):
    if key in regex_slots:
      overrides.pop(key, None)
  if "neighborhood" in regex_slots and "district" not in regex_slots:
    overrides.pop("district", None)
  if "station_name" in regex_slots:
    overrides.pop("station_name", None)
  elif should_keep_generic_transport_slot(regex_slots, query):
    overrides.pop("station_name", None)
  elif should_ignore_llm_station_name(overrides.get("station_name"), slots.get("neighborhood") or overrides.get("neighborhood"), query):
    overrides.pop("station_name", None)
  if should_keep_generic_education_slot(regex_slots, query):
    overrides.pop("school_name", None)
    overrides.pop("school_type", None)
    overrides.pop("school_types", None)
  slots.update(overrides)
  return slots


def should_keep_generic_transport_slot(regex_slots: dict[str, Any], query: str) -> bool:
  infra_preferences = regex_slots.get("infra_preferences")
  return (
    isinstance(infra_preferences, list)
    and "transport" in infra_preferences
    and "station_name" not in regex_slots
    and any(keyword in query for keyword in ("지하철역", "전철역", "역 근처", "역 주변", "역 인근", "역세권"))
  )


def should_keep_generic_education_slot(regex_slots: dict[str, Any], query: str) -> bool:
  infra_preferences = regex_slots.get("infra_preferences")
  return (
    isinstance(infra_preferences, list)
    and "education" in infra_preferences
    and "school_name" not in regex_slots
    and "school_type" not in regex_slots
    and "school_types" not in regex_slots
    and any(keyword in query for keyword in ("학교", "교육", "학군"))
  )


def should_ignore_llm_station_name(station_name: Any, neighborhood: Any, query: str) -> bool:
  if station_name is None:
    return False
  candidate = str(station_name).strip()
  if not candidate:
    return True
  if looks_like_generic_station_reference(candidate):
    return True
  neighborhood_name = str(neighborhood or "").strip()
  if neighborhood_name and candidate == neighborhood_name:
    return True
  if neighborhood_name and candidate == f"{neighborhood_name}역":
    return True
  return (
    neighborhood_name
    and f"{neighborhood_name}의" in query
    and any(keyword in query for keyword in ("지하철역", "전철역", "역 근처", "역 주변", "역 인근"))
    and "역" not in candidate
  )
