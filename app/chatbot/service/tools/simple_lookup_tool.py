from __future__ import annotations

from typing import Any

from langchain.tools import tool
from sqlalchemy.orm import Session

from app.chatbot.features.simple_lookup.service import run_simple_lookup
from .utils import compact_none


def build_simple_lookup_tool(session: Session):
  @tool
  def simple_lookup(
    query: str,
    query_type: str | None = None,
    complex_name: str | None = None,
    pyeong: int | None = None,
    area: float | None = None,
    period: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
    sort_order: str | None = None,
    price_order: str | None = None,
  ) -> dict[str, Any]:
    """
    아파트 단지의 위치, 주소, 실거래 내역, 최고가, 최저가 같은 단순 조회 질문을 처리합니다.
    "얼마야", "요즘 얼마야", "최근 얼마야", "시세 알려줘", "최근 실거래가", "거래내역"처럼
    현재 가격이나 최근 거래를 묻는 단지 질문은 query_type="trade"로 처리하세요.
    단, "추이", "흐름", "변화", "상승률", "하락률" 같은 변화 분석 표현이 함께 없으면
    "요즘", "시세"라는 단어가 있어도 query_type="trade"로 처리하세요.
    최고가/최저가 질문도 query_type="trade"로 처리하고 price_order를 함께 전달하세요.
    "최고가", "가장 비싼 거래", "제일 비싼 실거래가"는 price_order="highest"입니다.
    "최저가", "가장 싼 거래", "제일 싸게 거래된 실거래가"는 price_order="lowest"입니다.
    price_order에는 기본값을 두지 마세요. 최고가/최저가 표현이 있을 때만 채우세요.
    최고가/최저가 질문에서도 사용자가 "2023년까지", "최근 1년", "2020년 이후"처럼 기간을 말하면
    start_date/end_date/period를 함께 전달하세요.
    "㎡", "m2", "제곱미터"가 붙은 숫자는 반드시 area에 넣고 pyeong에 넣지 마세요.
    "평", "평형"이 붙은 숫자만 pyeong에 넣으세요.
    "개포주공 위치"처럼 위치/주소 표현 앞에 단지명으로 볼 수 있는 말이 있으면 반드시 complex_name에 넣으세요.
    단지명이 넓거나 여러 단지를 포함할 수 있어도 complex_name을 생략하지 마세요.
    예: "개포주공 위치"는 query_type="location", complex_name="개포주공"입니다.
    "신고가", "신고가 갱신", "신저가"는 단순 최고가/최저가 조회와 다르므로 처리하지 마세요.
    "몇 동이 제일 좋아?", "어느 동 추천해?", "살기 좋은 동"처럼 주관적 선호나 추천을 묻는 질문은 처리하지 마세요.

    Args:
      query: 사용자가 입력한 단순 조회 질문입니다. 예: "잠실엘스 어디 있어?"
      query_type: 조회 유형입니다. location 또는 trade 중 하나입니다.
      complex_name: 조회할 아파트 단지명입니다.
        여러 단지를 포함할 수 있는 넓은 이름이어도 생략하지 마세요. 예: "개포주공 위치" -> "개포주공"
      pyeong: 사용자가 지정한 단일 평형입니다.
        "평", "평형"이 붙은 숫자만 pyeong입니다.
      area: 사용자가 지정한 단일 전용면적(㎡)입니다.
        "㎡", "m2", "제곱미터"가 붙은 숫자는 반드시 area입니다.
      period: 상대 조회 기간입니다. 예: 3m, 1y
      start_date: 조회 시작일입니다. YYYY-MM-DD 형식입니다.
        사용자가 "부터", "이후", "부터 지금까지"처럼 시작 시점만 말하면 start_date만 채우고 end_date는 생략하세요.
      end_date: 조회 종료일입니다. YYYY-MM-DD 형식입니다.
        사용자가 종료 시점을 명시하지 않았으면 end_date를 절대 추측하지 마세요.
        사용자가 "23년도까지", "2023년까지", "2023년 말까지"처럼 종료 시점을 말하면 end_date를 채우세요.
        "23년도까지"는 end_date="2023-12-31"로 해석하세요.
      limit: 반환할 최대 거래 건수입니다.
      sort_order: 실거래 내역 정렬 방향입니다. latest 또는 oldest 중 하나입니다.
        "최근", "최신", 일반 거래내역 질문은 latest입니다.
        "가장 오래된", "제일 오래된", "최초", "처음" 거래 질문은 oldest입니다.
        price_order가 있으면 sort_order는 가격 동률 시 날짜 기준 보조 정렬입니다.
      price_order: 조회 조건 내 최고가/최저가 거래 정렬 방향입니다. highest 또는 lowest 중 하나입니다.
        최고가 질문은 highest이고 최저가 질문은 lowest입니다.
        기본값은 없습니다. 최고가/최저가 표현이 있을 때만 전달하세요.

    Returns:
      dict: simple_lookup service가 반환한 구조화된 JSON 결과입니다.
    """
    slots = compact_none({
      "original_question": query,
      "query_type": query_type,
      "complex_name": complex_name,
      "pyeong": pyeong,
      "area": area,
      "period": period,
      "start_date": start_date,
      "end_date": end_date,
      "limit": limit,
      "sort_order": sort_order,
      "price_order": price_order,
    })
    return run_simple_lookup(session, slots, query)

  return simple_lookup
