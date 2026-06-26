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
    analysis_type: str,
    target_type: str,
    target_name: str,
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
    단일 단지/지역의 시세추이와 지역 내 아파트 가격 순위를 조회합니다.

    반드시 이 tool을 쓰는 질문:
    - "은마아파트 시세추이", "강남구 시세추이", "서초구 최근 1년 시세 흐름"
    - "강남 3구 시세추이"
    - "강남구에서 많이 오른 아파트 TOP 5", "서초구에서 많이 내린 아파트 5곳"
    - "강남구 최고가 아파트 TOP 5", "서초구에서 가장 비싼 아파트"
    - "송파구 최저가 아파트 5곳", "송파구에서 가장 싼 아파트"

    시세추이 슬롯:
    - 시세추이/시세 흐름/기간별 흐름: analysis_type="timeseries"
    - 단지는 target_type="complex", 지역은 target_type="region"
    - 대상은 target_name 하나만 넣습니다.
    - "강남 3구"는 target_type="region", target_name="강남3구"

    지역 가격 순위 슬롯:
    - 지역 + 많이 오른/상승률 높은 아파트: analysis_type="ranking", rank_by="change_rate", direction="desc"
    - 지역 + 많이 내린/하락률 높은 아파트: analysis_type="ranking", rank_by="change_rate", direction="asc"
    - 지역 + 최고가/가장 비싼 아파트: analysis_type="ranking", rank_by="max_deal_amount", direction="desc"
    - 지역 + 최저가/가장 싼 아파트: analysis_type="ranking", rank_by="min_deal_amount", direction="asc"
    - "TOP 5", "5곳"은 limit=5입니다. 개수가 없으면 limit은 생략합니다.

    다른 tool로 보내지 말아야 하는 질문:
    - "서초구에서 가장 비싼 아파트 보여줘"는 단지 실거래 단순조회가 아니라 지역 가격 순위입니다.
    - "송파구 최저가 아파트 5곳 알려줘"는 단지 실거래 단순조회가 아니라 지역 가격 순위입니다.

    기간/면적:
    - "최근 1년"은 period="1y", "최근 6개월"은 period="6m"
    - "34평"은 pyeong=34, "84㎡"는 area=84
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
    return run_price_trend(session, slots, query)

  return analyze_price_trend


def _merge_slots(regex_slots: dict[str, Any], llm_slots: dict[str, Any]) -> dict[str, Any]:
  slots = dict(regex_slots)
  if "period" in regex_slots or "start_date" in regex_slots or "end_date" in regex_slots:
    llm_slots.pop("period", None)
    llm_slots.pop("start_date", None)
    llm_slots.pop("end_date", None)
  slots.update(llm_slots)
  return slots


def _target_name(target_type: str, target_name: str) -> str:
  name = " ".join(target_name.split())
  if target_type == "complex" and name.endswith("아파트"):
    return name[: -len("아파트")]
  return name
