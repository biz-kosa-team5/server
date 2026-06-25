from __future__ import annotations

from typing import Any

from langchain.tools import tool
from sqlalchemy.orm import Session

from app.chatbot.features.price_trend.service import run_price_trend
from app.chatbot.features.price_trend.slots import extract_price_trend_slots
from .utils import compact_none


def build_price_trend_tool(session: Session):
  @tool
  def analyze_price_trend(
    query: str,
    query_type: str | None = None,
    complex_name: str | None = None,
    region_name: str | None = None,
    region_names: list[str] | None = None,
    area: float | None = None,
    area_min: float | None = None,
    area_max: float | None = None,
    pyeong: float | None = None,
    pyeong_min: float | None = None,
    pyeong_max: float | None = None,
    period: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    interval: str | None = None,
    change_direction: str | None = None,
    rank_order: str | None = None,
    limit: int | None = None,
  ) -> dict[str, Any]:
    """
    아파트 또는 지역의 실거래가 추이, 상승률/하락률 순위 질문을 처리합니다.
    이 tool은 "추이", "흐름", "변화", "상승률", "하락률", "월별", "연도별"처럼
    시간에 따른 변화 분석이 명시된 질문에 사용하세요.
    "요즘", "시세"라는 단어만으로는 이 tool을 선택하지 마세요.
    단순히 "얼마야", "요즘 얼마야", "최근 얼마야", "시세 알려줘", "최근 실거래가", "거래내역"처럼
    현재 가격이나 최근 거래를 묻는 단지 질문은 simple_lookup을 사용하세요.
    특정 단지의 시세추이는 area 또는 pyeong이 필요합니다.

    Args:
      query: 사용자가 입력한 가격 추이 질문입니다. 예: "최근 많이 오른 아파트 알려줘"
      query_type: 조회 유형입니다. complex_trend, region_trend, price_change_ranking, price_ranking 중 하나입니다.
      complex_name: 조회 대상 아파트 단지명입니다.
      region_name: 조회 대상 단일 지역명입니다.
      region_names: 함께 조회할 복수 지역명입니다.
      area: 사용자가 지정한 단일 전용면적(㎡)입니다.
      area_min: 전용면적 하한(㎡)입니다.
      area_max: 전용면적 상한(㎡)입니다.
      pyeong: 사용자가 지정한 단일 평형입니다.
      pyeong_min: 평형 범위 하한입니다.
      pyeong_max: 평형 범위 상한입니다.
      period: 상대 조회 기간입니다. 예: 6m, 3y
      start_date: 조회 시작일입니다. YYYY-MM-DD 형식입니다.
      end_date: 조회 종료일입니다. YYYY-MM-DD 형식입니다.
      interval: 시계열 집계 간격입니다. month, quarter, year 중 하나입니다.
      change_direction: 가격 변화율 순위 방향입니다. up 또는 down입니다.
      rank_order: 실거래가 순위 정렬 방향입니다. highest 또는 lowest입니다.
      limit: 반환할 최대 순위 개수입니다.

    Returns:
      dict: price_trend service가 반환한 구조화된 JSON 결과입니다.
    """
    slots = extract_price_trend_slots(query)
    slots.update(compact_none({
      "query_type": query_type,
      "complex_name": complex_name,
      "region_name": region_name,
      "region_names": region_names,
      "area": area,
      "area_min": area_min,
      "area_max": area_max,
      "pyeong": pyeong,
      "pyeong_min": pyeong_min,
      "pyeong_max": pyeong_max,
      "period": period,
      "start_date": start_date,
      "end_date": end_date,
      "interval": interval,
      "change_direction": change_direction,
      "rank_order": rank_order,
      "limit": limit,
    }))
    return run_price_trend(session, slots, query)

  return analyze_price_trend
