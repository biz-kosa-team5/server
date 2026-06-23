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
    complex_name: str | None = None,
    pyeong: float | None = None,
    area: float | None = None,
    period: str | None = None,
    limit: int | None = None,
  ) -> dict[str, Any]:
    """
    아파트 단지의 위치, 주소, 실거래 내역, 최고가 같은 단순 조회 질문을 처리합니다.

    Args:
      query: 사용자가 입력한 단순 조회 질문입니다. 예: "잠실엘스 어디 있어?"
      query_type: 조회 유형입니다. location, trade_history, record_high 중 하나입니다.
      complex_name: 조회할 아파트 단지명입니다.
      pyeong: 사용자가 지정한 단일 평형입니다.
      area: 사용자가 지정한 단일 전용면적(㎡)입니다.
      period: 상대 조회 기간입니다. 예: 3m, 1y
      limit: 반환할 최대 거래 건수입니다.

    Returns:
      dict: simple_lookup service가 반환한 구조화된 JSON 결과입니다.
    """
    slots = extract_simple_lookup_slots(query)
    slots.update(compact_none({
      "query_type": query_type,
      "complex_name": complex_name,
      "pyeong": pyeong,
      "area": area,
      "period": period,
      "limit": limit,
    }))
    return run_simple_lookup(session, slots, query)

  return simple_lookup
