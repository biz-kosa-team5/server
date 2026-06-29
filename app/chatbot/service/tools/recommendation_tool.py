from __future__ import annotations

from typing import Any

from langchain.tools import tool
from sqlalchemy.orm import Session

from app.chatbot.features.recommendation.service import run_recommendation
from app.chatbot.features.recommendation.slots import extract_recommendation_slots
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
    sort_by: str | None = None,
    limit: int | None = None,
  ) -> dict[str, Any]:
    """
    지역, 가격, 역세권, 신축 여부 같은 조건에 맞는 아파트 추천 질문을 처리합니다.

    Args:
      query: 사용자가 입력한 아파트 추천 질문입니다. 예: "송파구 40억 이하 아파트 추천해줘"
      district: 추천 대상 구 이름입니다. 예: 송파구
      neighborhood: 추천 대상 동 이름입니다. 예: 잠실동
      station_name: 가까워야 하는 역 이름입니다. 예: 잠실역
      school_type: 가까워야 하는 단일 학교 유형입니다.
      school_types: 가까워야 하는 복수 학교 유형입니다.
      radius_m: 역/학교/인프라 반경입니다. 단위는 m입니다.
      min_price: 최소 매매가입니다. 단위는 만원입니다.
      max_price: 최대 매매가입니다. 단위는 만원입니다.
      min_households: 최소 세대수입니다.
      min_pyeong: 최소 평형입니다.
      max_pyeong: 최대 평형입니다.
      is_new_build: 신축/준신축 조건 여부입니다.
      min_built_year: 최소 준공연도입니다.
      infra_preferences: transport, education, commercial 중 선호 인프라 목록입니다.
      sort_by: 정렬 기준입니다. 예: distance_asc, price_asc, price_desc, school_distance_asc
      limit: 반환할 최대 후보 개수입니다.

    Returns:
      dict: recommendation service가 반환한 구조화된 JSON 결과입니다.
    """
    slots = extract_recommendation_slots(query)
    slots.update(compact_none({
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
      "sort_by": sort_by,
      "limit": limit,
    }))
    return run_recommendation(session, slots, query)

  return recommend_apartments
