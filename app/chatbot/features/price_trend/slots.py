"""시세추이 질문에서 기본 슬롯을 추출한다."""

from __future__ import annotations

import re
from typing import Any

from app.chatbot.features.price_trend.dto import (
    QUERY_COMPLEX_TREND,
    QUERY_PRICE_CHANGE_RANKING,
    QUERY_REGION_TREND,
)


DEFAULT_REGION_NAMES = ["강남구", "서초구", "송파구"]


def extract_price_trend_slots(question: str) -> dict[str, Any]:
    """자연어 질문에서 H4 기본 슬롯을 추출한다."""

    text = question.strip()
    query_type = infer_query_type(text)

    slots: dict[str, Any] = {
        "original_question": text,
        "query_type": query_type,
    }

    if query_type == QUERY_COMPLEX_TREND:
        complex_name = extract_complex_name(text)
        if complex_name is not None:
            slots["complex_name"] = complex_name
    else:
        regions = extract_region_names(text)
        if len(regions) == 1:
            slots["region_name"] = regions[0]
        else:
            slots["region_names"] = regions

    if query_type == QUERY_PRICE_CHANGE_RANKING:
        slots["change_direction"] = (
            "down"
            if any(token in text for token in ("하락", "내린", "떨어진"))
            else "up"
        )

    area = re.search(r"(\d+(?:\.\d+)?)\s*(?:㎡|m²|m2|제곱미터)", text, re.IGNORECASE)
    if area is not None:
        slots["area"] = float(area.group(1))

    pyeong = re.search(r"(\d+(?:\.\d+)?)\s*평", text)
    if pyeong is not None:
        slots["pyeong"] = float(pyeong.group(1))

    period = re.search(r"최근\s*(\d+)\s*(개월|달|년)", text)
    if period is not None:
        unit = "y" if period.group(2) == "년" else "m"
        slots["period"] = f"{period.group(1)}{unit}"

    limit = re.search(r"(\d+)\s*(?:개|곳|위)", text)
    if limit is not None and query_type == QUERY_PRICE_CHANGE_RANKING:
        slots["limit"] = int(limit.group(1))

    return slots


def infer_query_type(text: str) -> str:
    """질문 문구로 H4 query_type을 추론한다."""

    if any(
        token in text
        for token in ("많이 오른", "많이 내린", "상승률", "하락률", "오른 곳", "내린 곳")
    ):
        return QUERY_PRICE_CHANGE_RANKING

    if (
        any(region in text for region in DEFAULT_REGION_NAMES)
        or "강남 3구" in text
        or "강남3구" in text
    ):
        return QUERY_REGION_TREND

    return QUERY_COMPLEX_TREND


def extract_region_names(text: str) -> list[str]:
    """질문에서 강남3구 지역명을 추출한다."""

    if "강남 3구" in text or "강남3구" in text:
        return DEFAULT_REGION_NAMES

    regions = [region for region in DEFAULT_REGION_NAMES if region in text]
    return regions or DEFAULT_REGION_NAMES


def extract_complex_name(text: str) -> str | None:
    """단지 시세추이 질문에서 단지명 후보를 추출한다."""

    cleaned = re.sub(
        r"\d+(?:\.\d+)?\s*(?:㎡|m²|m2|제곱미터)",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\d+(?:\.\d+)?\s*(?:평|개|곳|위)", " ", cleaned)
    cleaned = re.sub(r"최근\s*\d+\s*(?:개월|달|년)", " ", cleaned)
    cleaned = re.sub(
        r"(시세\s*추이|시세|추이|가격|얼마|변화|흐름|거래|알려줘|보여줘|궁금해|\?)",
        " ",
        cleaned,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned or None


__all__ = [
    "extract_price_trend_slots",
    "extract_complex_name",
    "extract_region_names",
    "infer_query_type",
]
