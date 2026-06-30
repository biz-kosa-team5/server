"""시세추이 슬롯 추출 호환 모듈.

현재 슬롯 추출은 LLM tool arguments가 담당한다.
이 모듈은 기존 import 호환을 위해 original_question만 보존한다.
"""

from __future__ import annotations

from typing import Any


def extract_price_trend_slots(question: str) -> dict[str, Any]:
    """원문 질문만 보존한다.

    기간, 대상, 면적, 랭킹 등 슬롯 추출은 LangChain tool arguments와
    service/policy 검증 단계에서 처리한다.
    """
    normalized = question.strip()
    if not normalized:
        return {}

    return {
        "original_question": normalized,
    }


__all__ = [
    "extract_price_trend_slots",
]
