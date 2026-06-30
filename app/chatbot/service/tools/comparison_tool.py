from __future__ import annotations

from typing import Any

from langchain.tools import tool
from sqlalchemy.orm import Session

from app.chatbot.features.comparison.service import run_comparison
from app.chatbot.features.comparison.slots import extract_compare_slots
from .utils import compact_none


def build_comparison_tool(session: Session):
  @tool
  def compare_apartments(
    query: str,
    apartment_names: list[str] | None = None,
    metrics: list[str] | None = None,
    school_type: str | None = None,
    infra_preferences: list[str] | None = None,
  ) -> dict[str, Any]:
    """
    둘 이상의 아파트 단지를 가격, 평형, 세대수, 연식, 교통, 교육 조건으로 비교합니다.
    단지명이 붙여 쓰였거나 일부 오타가 있어도 사용자가 쓴 단지명 후보를 apartment_names에 최대한 보존해서 넘깁니다.

    Args:
      query: 사용자가 입력한 아파트 비교 질문입니다. 예: "래미안대치팰리스랑 잠실엘스 비교해줘"
      apartment_names: 비교할 아파트 단지명 목록입니다.
      metrics: 비교 기준 목록입니다. 예: latest_price, pyeong, price_per_pyeong, households, built_year, nearest_station, nearest_school
      school_type: 교육 비교에 사용할 학교 유형입니다. 예: 초등학교
      infra_preferences: transport, education, commercial 중 비교할 인프라 목록입니다.

    Returns:
      dict: comparison service가 반환한 구조화된 JSON 결과입니다.
    """
    slots = extract_compare_slots(query)
    slots.update(compact_none({
      "apartment_names": apartment_names,
      "metrics": metrics,
      "school_type": school_type,
      "infra_preferences": infra_preferences,
    }))
    return run_comparison(session, slots, query)

  return compare_apartments
