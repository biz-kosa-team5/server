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
    analysis_type: str | None = None,
    target_type: str | None = None,
    target_name: str | None = None,
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
    rank_by: str | None = None,
    direction: str | None = None,
    limit: int | None = None,
  ) -> dict[str, Any]:
    """
    단지/지역의 시세추이와 지역 내 상승률/하락률 순위를 조회합니다.

    이 tool의 담당 범위:
    1. 단일 단지 시세추이
    2. 단일 지역 시세추이
    3. 강남 3구 시세추이
    4. 지역 내 상승률/하락률 아파트 순위

    반드시 이 tool을 쓰는 질문:
    - "은마아파트 시세추이", "반포자이 가격 흐름", "잠실엘스 최근 1년 시세추이"
    - "은마 월별 시세추이", "은마 분기별 시세추이", "은마 연도별 시세추이"
    - "강남구 시세추이", "서초구 최근 1년 시세 흐름", "송파구 연도별 시세추이"
    - "강남 3구 시세추이"
    - "강남구에서 많이 오른 아파트 TOP 5", "서초구 하락률 높은 아파트 5곳"

    query 규칙:
    - query에는 사용자의 원문 질문을 최대한 그대로 넣습니다.
    - 월별, 분기별, 연도별, 최근 1년, 최근 6개월, 면적, TOP N, 상승률, 하락률 같은 조건어를 제거하지 마세요.
    - 여러 지역을 각각 나눠 호출하더라도 조건어는 각 query와 슬롯에 반드시 유지하세요.
      예: "송파구, 강남구 연도별 시세추이"는
      "송파구 연도별 시세추이", "강남구 연도별 시세추이"처럼 처리합니다.

    target 규칙:
    - target_type은 단지면 "complex", 지역이면 "region"입니다.
    - target_name에는 순수한 대상명만 넣습니다.
    - target_name에 "시세추이", "TOP 5", "아파트", "가장 비싼", "가장 싼" 같은 조건어를 붙이지 마세요.
    - 예: "은마 연도별 시세추이" -> target_type="complex", target_name="은마"
    - "강남 3구"는 target_type="region", target_name="강남3구"입니다.

    시세추이 슬롯:
    - 시세추이/시세 흐름/가격 흐름/기간별 흐름: analysis_type="timeseries"
    - 사용자가 월별/분기별/연도별을 말하면 반드시 interval에 반영합니다.
    - "월별"은 interval="month"
    - "분기별"은 interval="quarter"
    - "연도별", "연간", "년도별"은 interval="year"
    - 사용자가 집계 간격을 말하지 않으면 interval은 생략합니다.

    지역 상승률/하락률 순위 슬롯
    - 지역 + 많이 오른/상승률 높은 아파트: analysis_type="ranking", rank_by="change_rate", direction="desc"
    - 지역 + 많이 내린/하락률 높은 아파트: analysis_type="ranking", rank_by="change_rate", direction="asc"
    - "TOP 5", "5곳", "5개"는 limit=5입니다.
    - "TOP 10", "10곳", "10개"는 limit=10입니다.
    - 개수가 없으면 limit은 생략합니다.

    simple_lookup으로 보내야 하는 질문:
    - "은마 최근 실거래가", "은마 거래내역", "은마 위치", "은마 주소"는 단순조회입니다.
    - "은마 최고가", "반포자이 최고가", "잠실엘스 최저가"처럼 특정 단지의 최고가/최저가 1건 조회는 simple_lookup입니다.

    기간/면적:
    - "최근 1년"은 period="1y", "최근 6개월"은 period="6m"
    - "2025년"처럼 특정 연도는 start_date="2025-01-01", end_date="2025-12-31"입니다.
    - "34평"은 pyeong=34, "30평대"는 pyeong_min=30, pyeong_max=39입니다.
    - "84㎡"는 area=84입니다.
    """
    slots = _merge_slots(
      extract_price_trend_slots(query),
      compact_none({
        "analysis_type": analysis_type,
        "target_type": target_type,
        "target_name": _target_name(target_type, target_name),
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
        "rank_by": rank_by,
        "direction": direction,
        "limit": limit,
      }),
    )
    return run_price_trend(session, slots)

  return analyze_price_trend


def _merge_slots(regex_slots: dict[str, Any], llm_slots: dict[str, Any]) -> dict[str, Any]:
  slots = dict(regex_slots)

  if "period" in regex_slots or "start_date" in regex_slots or "end_date" in regex_slots:
    llm_slots.pop("period", None)
    llm_slots.pop("start_date", None)
    llm_slots.pop("end_date", None)

  slots.update(llm_slots)
  return slots


def _target_name(target_type: str | None, target_name: str | None) -> str | None:
  if target_name is None:
    return None
  name = " ".join(target_name.split())
  if target_type == "complex" and name.endswith("아파트"):
    return name[: -len("아파트")]
  return name
