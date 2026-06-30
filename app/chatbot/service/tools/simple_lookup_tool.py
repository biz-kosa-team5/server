"""
단순 조회 기능을 LangChain tool로 감싼 adapter입니다.

LLM이 구조화 인자를 일부 생략해도 원문 query에서 기본 슬롯을 추출한 뒤,
LLM이 명시한 인자로 덮어씁니다.
"""

from __future__ import annotations

from typing import Any

from langchain.tools import tool
from sqlalchemy.orm import Session

from app.chatbot.features.simple_lookup.service import run_simple_lookup
from app.chatbot.features.simple_lookup.slots import extract_simple_lookup_slots
from .utils import compact_none


def build_simple_lookup_tool(session: Session):
    @tool
    def simple_lookup(
        query: str,
        query_type: str | None = None,
        target_name: str | None = None,
        pyeong: float | None = None,
        area: float | None = None,
        period: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
        sort_order: str | None = None,
        price_order: str | None = None,
    ) -> dict[str, Any]:
        """
        단순 조회 전용 tool입니다. 반드시 질문 의도에 맞는 query_type을 직접 선택해서 넘기세요.
        이 tool에 전달한 query_type은 slots.py가 추출한 기본 query_type을 덮어씁니다.

        query_type 선택 규칙:
        - location:
          특정 아파트/단지의 위치, 주소, 좌표를 묻는 질문입니다.
          예: "은마아파트 위치 알려줘"
          -> query_type="location", target_name="은마아파트"

        - trade_history:
          특정 아파트/단지의 실거래가, 거래내역, 최근 거래를 묻는 질문입니다.
          예: "은마아파트 84㎡ 지난 1년 거래내역 알려줘"
          -> query_type="trade_history", target_name="은마아파트", area=84, period="1y"
          예: "래미안대치팰리스 최근 6개월 거래 5건 보여줘"
          -> query_type="trade_history", target_name="래미안대치팰리스", period="6m", limit=5

        - region_trade_history:
          구/동 지역의 실거래가, 거래내역, 최근 거래를 묻는 질문입니다.
          최고가/최저가 순위가 아니라 단순 거래내역이면 이 값을 사용하세요.
          예: "서초구 59㎡ 지난 6개월 거래내역 보여줘"
          -> query_type="region_trade_history", target_name="서초구", area=59, period="6m"
          예: "대치동 최근 거래 10건 알려줘"
          -> query_type="region_trade_history", target_name="대치동", limit=10

        - complex_price_record:
          특정 아파트/단지 안에서 최고가 또는 최저가 거래를 묻는 질문입니다.
          예: "은마아파트 84㎡ 지난 1년 최고가 거래 알려줘"
          -> query_type="complex_price_record", target_name="은마아파트", area=84, period="1y", price_order="highest"
          예: "반포자이 최근 6개월 최저가 3건 보여줘"
          -> query_type="complex_price_record", target_name="반포자이", period="6m", price_order="lowest", limit=3

        - region_price_ranking:
          구/동 지역 안에서 최고가 또는 최저가 거래 순위/랭킹/N건을 묻는 질문입니다.
          예: "송파구 30평 최고가 거래 3건 알려줘"
          -> query_type="region_price_ranking", target_name="송파구", pyeong=30, price_order="highest", limit=3
          예: "서초구 59㎡ 지난 6개월 최저가 거래내역 보여줘"
          -> query_type="region_price_ranking", target_name="서초구", area=59, period="6m", price_order="lowest"

        기간/건수 규칙:
        - "지난 6개월", "최근 6개월" -> period="6m"
        - "지난 1년", "최근 1년" -> period="1y"
        - "3건", "5건", "TOP 5"처럼 거래 건수를 명시한 경우에만 limit을 넘기세요.
        - "최근 6개월"의 숫자 6은 기간 숫자이며 limit이 아닙니다.

        면적 규칙:
        - "84㎡", "84m2" -> area=84
        - "30평", "30평형" -> pyeong=30
        - "30평대"는 현재 단일 pyeong으로 정확히 표현할 수 없으므로 가능하면 pyeong을 생략하세요.

        정렬/가격 규칙:
        - "최고가", "가장 비싼" -> price_order="highest"
        - "최저가", "가장 싼" -> price_order="lowest"
        - "가장 오래된", "최초 거래" -> sort_order="oldest", query_type="trade_history" 또는 "region_trade_history"
        - 최고가/최저가 질문은 sort_order가 아니라 price_order를 사용하세요.

        아파트 단지의 위치, 단지 실거래 내역, 동/구 단위 최신 실거래 내역,
        단지 최고가/최저가, 지역 최고가/최저가 거래 랭킹을 조회합니다.

        지원하는 query_type:
        - location: 특정 단지의 주소, 위치, 좌표 조회
        - trade_history: 특정 단지의 실거래 내역, 최근 거래, 거래가 조회
        - region_trade_history: 특정 동/구의 최신 실거래 내역 조회
        - complex_price_record: 특정 단지의 최고가/최저가 거래 조회
        - region_price_ranking: 특정 지역의 최고가/최저가 거래 랭킹 조회

        query_type 선택 규칙:
        - "어디 있어?", "주소 알려줘", "위치 알려줘", "좌표 알려줘"는 query_type="location"입니다.
        - 특정 단지명을 대상으로 한 "찾아줘", "찾아주라", "찾아주세요"는 사용자가 단지 위치/기본 정보를 찾는 말일 수 있으므로
          query_type="location"으로 처리할 수 있습니다. 예: "반포자이 찾아줘" -> location, target_name="반포자이".
        - "아파트 찾아줘"처럼 대상 단지명이나 지역 조건이 없는 질문은 target_name을 억지로 만들지 마세요.
        - "얼마야", "요즘 얼마야", "최근 얼마야", "최근 실거래가", "거래내역"은 query_type="trade_history"입니다.
          - 특정 단지의 "가장 오래된 거래", "제일 오래된 거래", "최초 거래", "첫 거래", "처음 거래"는
          query_type="trade_history", sort_order="oldest", limit=1입니다.
          이 질문들은 최고가/최저가 질문이 아니므로 complex_price_record를 사용하지 말고 price_order도 전달하지 마세요.
          단, 대상이 "대치동", "잠실동", "강남구"처럼 동/구 지역이면 query_type="region_trade_history"입니다.
        - 특정 단지의 "최고가", "최저가", "가장 비싼 거래", "가장 싼 거래"는
          query_type="complex_price_record"입니다.
        - 특정 지역의 "최고가 거래 TOP 5", "최저가 거래 5건", "가장 비싼 아파트 5곳"은
          query_type="region_price_ranking"입니다.

        price_order 선택 규칙:
        - "최고가", "가장 비싼", "제일 비싼"은 price_order="highest"입니다.
        - "최저가", "가장 싼", "제일 싼", "제일 싸게 거래된"은 price_order="lowest"입니다.
        - complex_price_record와 region_price_ranking에서는 price_order를 함께 전달하세요.

        기간 표현 해석 규칙:
        - "2010년부터 5년간"같은 기간을 정할 수 있는 내용은  period로 전달하지 말고 start_date/end_date로 전달하세요.
          예: "2010년부터 5년간" -> start_date="2010-01-01", end_date="2014-12-31"
        - "최근 N개월", "지난 N개월"은 period="{N}m"으로 전달하세요.
          start_date/end_date로 변환하지 마세요.
          예: "최근 3개월" -> period="3m"
          예: "최근 6개월" -> period="6m"
        - "최근 N년", "지난 N년"은 period="{N}y"로 전달하세요.
          start_date/end_date로 변환하지 마세요.
          예: "최근 1년" -> period="1y"
          예: "지난 2년" -> period="2y"
        - "최근 6개월"의 숫자 6, "최근 1년"의 숫자 1은 기간 숫자입니다.
          limit으로 전달하지 마세요.
        - "최근 6개월 최고가", "최근 1년 최저가"처럼 기간과 최고가/최저가만 말한 경우,
          limit은 생략하세요.
        - "2020년 이후", "2020년부터"처럼 시작 시점만 말하면 start_date="2020-01-01"로 전달하세요.
        - "2023년까지", "2023년 말까지"처럼 종료 시점만 말하면 end_date="2023-12-31"로 전달하세요.
        - "2024년 거래내역", "2024년 실거래가"처럼 특정 연도 전체를 말하면
          start_date="2024-01-01", end_date="2024-12-31"로 전달하세요.

        limit 해석 규칙:
        - limit은 반환할 거래 건수입니다.
        - "3건", "5건", "10건", "TOP 5", "5곳"처럼 개수를 명시한 경우에만 limit을 전달하세요.
        - "최근 3개월", "최근 6개월", "최근 1년"의 숫자는 기간 숫자이므로 limit으로 전달하지 마세요.
        - "최고가 알려줘", "최저가 알려줘"처럼 개수를 말하지 않으면 limit은 생략하세요.
          기본 개수는 policy에서 처리합니다.
        - "은마 최고가 3건 알려줘"처럼 거래 건수를 말한 경우에만 limit=3입니다.

        주요 예시:
        - "잠실엘스 위치 알려줘"
          -> query_type="location", target_name="잠실엘스"

        - "반포자이 찾아줘"
          -> query_type="location", target_name="반포자이"

        - "은마 최근 실거래가 알려줘"
          -> query_type="trade_history", target_name="은마"

        - "은마 최근 3개월 거래내역 5건 알려줘"
          -> query_type="trade_history", target_name="은마", period="3m", limit=5

        - "대치동 최신 실거래가 3개 알려줘"
          -> query_type="region_trade_history", target_name="대치동", limit=3

        - "강남구 최근 실거래 10건 알려줘"
          -> query_type="region_trade_history", target_name="강남구", limit=10

        - "반포자이 최근 6개월 최고가 알려줘"
          -> query_type="complex_price_record", target_name="반포자이",
             period="6m", price_order="highest"
          -> limit은 전달하지 마세요.

        - "잠실엘스 최근 1년 최저가 알려줘"
          -> query_type="complex_price_record", target_name="잠실엘스",
             period="1y", price_order="lowest"
          -> limit은 전달하지 마세요.

        - "은마 최고가 3건 알려줘"
          -> query_type="complex_price_record", target_name="은마",
             price_order="highest", limit=3

        - "강남구 최근 1년 최고가 거래 TOP 5 알려줘"
          -> query_type="region_price_ranking", target_name="강남구",
             period="1y", price_order="highest", limit=5

        - "송파구 최근 6개월 최저가 거래 5건 알려줘"
          -> query_type="region_price_ranking", target_name="송파구",
             period="6m", price_order="lowest", limit=5

        - "송파구 2020년 최저가"
          -> query_type="region_price_ranking", target_name="송파구",
            price_order="lowest", start_date="2020-01-01", end_date="2020-12-31"

        면적/평형 해석 규칙:
        - "㎡", "m2", "제곱미터"가 붙은 숫자는 area에 넣으세요.
          예: "84㎡" -> area=84
        - "평", "평형"이 붙은 숫자는 pyeong에 넣으세요.
          예: "30평" -> pyeong=30
        - area와 pyeong을 동시에 전달하지 마세요.

        target_name 해석 규칙:
        - 단지 조회에서는 아파트 단지명을 target_name에 넣으세요.
          예: "은마", "반포자이", "잠실엘스"
        - 조사, 말끝, 어색한 중복 표현은 target_name에 포함하지 말고 query 원문에만 보존하세요.
        - 지역 랭킹에서는 지역명을 target_name에 넣으세요.
          예: "강남구", "서초구", "송파구"
        - 지역 조회에서는 동/구명을 target_name에 넣으세요.
          예: "대치동", "잠실동", "강남구"
        - "강남 최고가 거래 TOP 5"처럼 "구"가 빠져도 target_name="강남"으로 전달할 수 있습니다.

        sort_order 해석 규칙:
        - trade_history에서 날짜 정렬 방향을 나타냅니다.
        - "최근", "최신", 일반 거래내역 질문은 sort_order="latest"입니다.
        - "가장 오래된", "제일 오래된", "최초", "처음" 거래 질문은 sort_order="oldest"입니다.
        - location과 region_price_ranking에서는 sort_order를 전달하지 마세요.
        - region_trade_history는 기본적으로 최신순입니다.
        - complex_price_record에서는 가격이 같은 거래의 날짜 보조 정렬로 사용할 수 있습니다.

        처리하지 말아야 할 질문:
        - "추이", "흐름", "변화", "상승률", "하락률", "월별", "연도별"처럼 변화 분석을 요구하는 질문
        - "신고가", "신고가 갱신", "신저가"처럼 기존 거래 대비 갱신 여부를 묻는 질문
        - "몇 동이 제일 좋아?", "어느 동 추천해?", "살기 좋은 동"처럼 주관적 선호나 추천을 묻는 질문

        Args:
            query: 
              사용자가 입력한 단순조회 질문입니다.
              원문 질문을 그대로 넣으세요.
            query_type:
                필수 인자 입니다.
                조회 유형입니다.
                location, trade_history, region_trade_history, complex_price_record, region_price_ranking 중 하나입니다.
            target_name:
                조회 대상 단지명 또는 지역명을 반드시 넣어야 하는 필수 인자입니다..
                조회 대상 이름입니다.
                단지 조회에서는 아파트 단지명입니다.
                지역 랭킹에서는 지역명입니다.
                query에 대상명이 있으면 target_name을 비워두지 마세요.
            pyeong: 사용자가 지정한 단일 평형입니다.
                "평", "평형"이 붙은 숫자만 pyeong입니다.
            area: 사용자가 지정한 단일 전용면적(㎡)입니다.
                "㎡", "m2", "제곱미터"가 붙은 숫자는 area입니다.
            period: 상대 조회 기간입니다. 예: 3m, 6m, 1y
                "최근 N개월", "지난 N개월"은 period="{N}m"입니다.
                "최근 N년", "지난 N년"은 period="{N}y"입니다.
                이런 표현은 start_date/end_date로 바꾸지 마세요.
            start_date: 조회 시작일입니다. YYYY-MM-DD 형식입니다.
                "2020년 이후", "2020년부터"처럼 시작 시점만 명시한 경우에 사용하세요.
                "최근 N개월", "최근 N년"에는 사용하지 마세요.
            end_date: 조회 종료일입니다. YYYY-MM-DD 형식입니다.
                "2023년까지", "2023년 말까지"처럼 종료 시점만 명시한 경우에 사용하세요.
                "최근 N개월", "최근 N년"에는 사용하지 마세요.
            limit: 반환할 최대 거래 건수입니다.
                "3건", "5건", "TOP 5", "5곳"처럼 개수를 명시한 경우에만 전달하세요.
                "최근 3개월", "최근 6개월", "최근 1년"의 숫자는 기간 숫자이므로 limit으로 전달하지 마세요.
            sort_order: 실거래 내역 날짜 정렬 방향입니다. latest 또는 oldest 중 하나입니다.
            price_order: 최고가/최저가 정렬 방향입니다. highest 또는 lowest 중 하나입니다.

        Returns:
            dict: simple_lookup service가 반환한 구조화된 JSON 결과입니다.
        """
        slots = extract_simple_lookup_slots(query)

        slots.update(compact_none({
            "query_type": query_type,
            "target_name": target_name,
            "pyeong": pyeong,
            "area": area,
            "period": period,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
            "sort_order": sort_order,
            "price_order": price_order,
        }))

        return run_simple_lookup(session, slots, query)

    return simple_lookup
