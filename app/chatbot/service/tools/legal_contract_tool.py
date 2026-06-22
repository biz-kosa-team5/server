from __future__ import annotations

from typing import Any

from langchain.tools import tool
from sqlalchemy.orm import Session

from app.chatbot.features.legal_contract.service import run_legal_contract
from app.chatbot.features.legal_contract.slots import extract_legal_contract_slots
from .utils import compact_none


def build_legal_contract_tool(session: Session):
  @tool
  def search_legal_contract(
    query: str,
    original_query: str | None = None,
    normalized_query: str | None = None,
  ) -> dict[str, Any]:
    """
    부동산 매매, 전세, 임대차 계약과 관련된 법령 근거 검색 질문을 처리합니다.

    Args:
      query: 사용자가 입력한 계약/법률 질문입니다. 예: "매매 계약금 해제 규정 알려줘"
      original_query: 법률 검색에 사용할 원문 질문입니다.
      normalized_query: 정규화된 법률 검색 질문입니다.

    Returns:
      dict: legal_contract service가 반환한 구조화된 JSON 결과입니다.
    """
    slots = extract_legal_contract_slots(query)
    slots.update(compact_none({
      "original_query": original_query,
      "normalized_query": normalized_query,
    }))
    return run_legal_contract(session, slots, query)

  return search_legal_contract
