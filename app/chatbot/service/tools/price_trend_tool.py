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
    - "경덕아파트 2015년부터 시세추이", "은마아파트 2015년부터 2020년까지 월별 시세 추이"
    - "은마 월별 시세추이", "은마 분기별 시세추이", "은마 연도별 시세추이"
    - "강남구 시세추이", "서초구 최근 1년 시세 흐름", "송파구 연도별 시세추이", "대치동 최근 1년 시세추이"
    - "강남 3구 시세추이"
    - "강남구에서 많이 오른 아파트 TOP 5", "대치동에서 많이 오른 아파트 TOP 5", "서초구 하락률 높은 아파트 5곳"

    query 규칙:
    - query에는 사용자의 원문 질문을 그대로 넣습니다.
    - query를 요약하거나 자연스럽게 고쳐 쓰지 마세요.
    - "부터", "이후", "까지", "최근", "지난", "월별", "분기별", "연도별", "평대", "㎡", "TOP N" 같은 조건 표현을 제거하지 마세요.
    - 예: 사용자가 "경덕아파트 2015년부터 시세추이"라고 물으면 query="경덕아파트 2015년부터 시세추이"입니다.
    - 잘못된 예: query="경덕아파트 2015년 시세추이"

    analysis_type 선택 규칙:
    - analysis_type은 필수 인자입니다. 이 tool을 호출할 때 생략하지 마세요.
    - 단지/지역의 "시세추이", "시세 추이", "시세 흐름", "가격 추이", "가격 흐름", "가격 변화", "실거래가 추이"는
      analysis_type="timeseries"입니다.
    - 지역 안에서 "많이 오른", "상승률 높은", "오른 아파트", "많이 내린", "하락률 높은", "내린 아파트",
      "순위", "랭킹", "TOP"을 묻는 질문은 analysis_type="ranking"입니다.

    target 규칙:
    - target_type은 필수 인자입니다. 생략하지 마세요.
    - target_name은 필수 인자입니다. query에 대상명이 있으면 비워두지 마세요.
    - 특정 단지의 시세추이는 target_type="complex"입니다.
      예: "은마아파트", "경덕아파트", "반포자이", "래미안대치팰리스"
    - 특정 지역의 시세추이나 순위는 target_type="region"입니다.
      예: "강남구", "서초구", "송파구", "대치동", "반포동", "강남 3구"
    - target_name에는 순수한 대상명만 넣습니다.
    - target_name에 "시세추이", "가격 흐름", "TOP 5", "많이 오른", "많이 내린" 같은 조건어를 넣지 마세요.
    - 예: "경덕아파트 2015년부터 시세추이" -> target_type="complex", target_name="경덕"
    - 예: "은마 연도별 시세추이" -> target_type="complex", target_name="은마"
    - 예: "반포자이 최근 5년 가격 흐름" -> target_type="complex", target_name="반포자이"
    - 예: "강남구 최근 1년 시세추이" -> target_type="region", target_name="강남구"
    - "강남 3구", "강남3구", "강남삼구"는 target_type="region", target_name="강남3구"입니다.

    시세추이 슬롯 규칙:
    - analysis_type="timeseries"는 단지/지역의 가격 흐름을 기간별로 조회하는 질문입니다.
    - 사용자가 "월별"이라고 말하면 interval="month"입니다.
    - 사용자가 "분기별"이라고 말하면 interval="quarter"입니다.
    - 사용자가 "연도별", "년도별", "연간"이라고 말하면 interval="year"입니다.
    - 사용자가 집계 간격을 말하지 않으면 interval은 생략합니다.
    - analysis_type="ranking"인 질문에서는 interval을 전달하지 마세요.

    지역 상승률/하락률 순위 슬롯 규칙:
    - analysis_type="ranking"은 특정 지역 안에서 상승률/하락률이 높은 아파트 순위를 조회하는 질문입니다.
    - ranking 질문은 반드시 target_type="region"입니다.
    - 지역 + "많이 오른", "상승률 높은", "오른 아파트"는
      analysis_type="ranking", rank_by="change_rate", direction="desc"입니다.
    - 지역 + "많이 내린", "하락률 높은", "내린 아파트"는
      analysis_type="ranking", rank_by="change_rate", direction="asc"입니다.
    - 상승률/하락률 순위 질문에서는 rank_by="change_rate"를 반드시 전달하세요.
    - "TOP 5", "5곳", "5개"는 limit=5입니다.
    - "TOP 10", "10곳", "10개"는 limit=10입니다.
    - 개수를 말하지 않으면 limit은 생략합니다.
    - "최근 1년 많이 오른 아파트 TOP 5"에서 1은 period 숫자이고, 5는 limit 숫자입니다.

    기간/면적 규칙:
    - "최근 N개월", "지난 N개월"은 period="{N}m"으로 전달합니다.
      예: "최근 6개월" -> period="6m"
    - "최근 N년", "지난 N년"은 period="{N}y"로 전달합니다.
      예: "최근 1년" -> period="1y"
      예: "최근 5년" -> period="5y"
    - "N개월간", "N개월 동안"은 period="{N}m"으로 전달합니다.
    - "N년간", "N년 동안"은 period="{N}y"로 전달합니다.
      예: "10년간" -> period="10y"
    - "최근 6개월"의 숫자 6, "최근 1년"의 숫자 1은 기간 숫자입니다. limit으로 전달하지 마세요.
    - "2025년"처럼 특정 연도만 말하면 start_date="2025-01-01", end_date="2025-12-31"입니다.
    - "2015년부터", "2015년 이후"처럼 시작 시점만 말하면 start_date="2015-01-01"만 넣고 end_date는 생략합니다.
    - "2020년까지", "2020년 말까지"처럼 종료 시점만 말하면 end_date="2020-12-31"만 넣고 start_date는 생략합니다.
    - "2015년부터 2020년까지"처럼 시작/종료가 모두 있으면 start_date="2015-01-01", end_date="2020-12-31"입니다.
    - period와 start_date/end_date는 동시에 넣지 않습니다.
    - 상대 기간은 period를 사용하고, 절대 기간은 start_date/end_date를 사용합니다.
    - "34평"은 pyeong=34입니다.
    - "30평대"는 pyeong_min=30, pyeong_max=39입니다.
    - "25~30평", "25평에서 30평"은 pyeong_min=25, pyeong_max=30입니다.
    - "84㎡", "84제곱", "84제곱미터"는 area=84입니다.
    - "59~84㎡", "59에서 84제곱"은 area_min=59, area_max=84입니다.
    - area와 pyeong을 동시에 전달하지 마세요.

    주요 예시:
    - "경덕아파트 2015년부터 시세추이"
      -> analysis_type="timeseries", target_type="complex", target_name="경덕", start_date="2015-01-01"

    - "은마아파트 2015년부터 2020년까지 월별 시세 추이"
      -> analysis_type="timeseries", target_type="complex", target_name="은마",
         start_date="2015-01-01", end_date="2020-12-31", interval="month"

    - "경덕아파트 2020년까지 시세추이"
      -> analysis_type="timeseries", target_type="complex", target_name="경덕", end_date="2020-12-31"

    - "반포자이 2024년 시세추이"
      -> analysis_type="timeseries", target_type="complex", target_name="반포자이",
         start_date="2024-01-01", end_date="2024-12-31"

    - "래미안대치팰리스 최근 5년 가격 흐름"
      -> analysis_type="timeseries", target_type="complex", target_name="래미안대치팰리스", period="5y"

    - "강남구 최근 5년 시세추이"
      -> analysis_type="timeseries", target_type="region", target_name="강남구", period="5y"

    - "서초구 10년간 시세추이"
      -> analysis_type="timeseries", target_type="region", target_name="서초구", period="10y"

    - "대치동 최근 1년 시세추이"
      -> analysis_type="timeseries", target_type="region", target_name="대치동", period="1y"

    - "강남 3구 연도별 시세추이"
      -> analysis_type="timeseries", target_type="region", target_name="강남3구", interval="year"

    - "반포자이 30평대 2018년부터 시세추이"
      -> analysis_type="timeseries", target_type="complex", target_name="반포자이",
         pyeong_min=30, pyeong_max=39, start_date="2018-01-01"

    - "압구정현대 84제곱 2021년부터 가격 변화"
      -> analysis_type="timeseries", target_type="complex", target_name="압구정현대",
         area=84, start_date="2021-01-01"

    - "강남구 최근 1년 많이 오른 아파트 TOP 5"
      -> analysis_type="ranking", target_type="region", target_name="강남구",
         period="1y", rank_by="change_rate", direction="desc", limit=5

    - "대치동에서 많이 오른 아파트 TOP 5"
      -> analysis_type="ranking", target_type="region", target_name="대치동",
         rank_by="change_rate", direction="desc", limit=5

    - "서초구 하락률 높은 아파트 10곳"
      -> analysis_type="ranking", target_type="region", target_name="서초구",
         rank_by="change_rate", direction="asc", limit=10

    simple_lookup으로 보내야 하는 질문:
    - "은마 최근 실거래가", "은마 거래내역", "은마 위치", "은마 주소"는 단순조회입니다.
    - "은마 얼마야", "반포자이 최근 거래 알려줘"는 단순조회입니다.
    - "은마 최고가", "반포자이 최고가", "잠실엘스 최저가"처럼 특정 단지의 최고가/최저가 1건 조회는 simple_lookup입니다.

    처리하지 말아야 할 질문:
    - 단지 위치, 주소, 좌표만 묻는 질문
    - 최근 실거래가, 거래내역, 최고가, 최저가 1건만 묻는 질문
    - 조건 기반 아파트 추천 질문
    - 둘 이상의 단지를 비교하는 질문
    - 부동산 계약, 법령, 임대차 관련 질문

    Args:
        query:
            사용자가 입력한 시세추이/가격변화/랭킹 질문입니다.
            원문 질문을 그대로 넣으세요.
        analysis_type:
            필수 인자입니다. timeseries 또는 ranking 중 하나입니다.
        target_type:
            필수 인자입니다. complex 또는 region 중 하나입니다.
        target_name:
            필수 인자입니다. 조회 대상 단지명 또는 지역명입니다.
        area:
            단일 전용면적(㎡)입니다.
        area_min:
            전용면적 범위의 최소값입니다.
        area_max:
            전용면적 범위의 최대값입니다.
        pyeong:
            단일 평형입니다.
        pyeong_min:
            평형 범위의 최소값입니다.
        pyeong_max:
            평형 범위의 최대값입니다.
        period:
            상대 조회 기간입니다. 예: 6m, 1y, 5y
        start_date:
            조회 시작일입니다. YYYY-MM-DD 형식입니다.
        end_date:
            조회 종료일입니다. YYYY-MM-DD 형식입니다.
        interval:
            시세추이 집계 간격입니다. month, quarter, year 중 하나입니다.
        rank_by:
            ranking 정렬 기준입니다. 상승률/하락률 순위는 change_rate입니다.
        direction:
            ranking 정렬 방향입니다. desc 또는 asc입니다.
        limit:
            ranking에서 반환할 최대 개수입니다.

    Returns:
        dict: price_trend service가 반환한 구조화된 JSON 결과입니다.
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
  slots.update(llm_slots)
  return slots


def _target_name(target_type: str | None, target_name: str | None) -> str | None:
  if target_name is None:
    return None
  name = " ".join(target_name.split())
  if target_type == "complex" and name.endswith("아파트"):
    return name[: -len("아파트")]
  return name
