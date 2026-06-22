from __future__ import annotations

import json
from typing import Any


MAX_ANSWER_SOURCES = 5
MAX_SOURCE_CONTENT_CHARS = 6000

SYSTEM_PROMPT = """당신은 대한민국 부동산 매매 관련 법률 정보를 설명하는 도우미입니다.
반드시 제공된 법령 조문만 근거로 답변하세요.
근거에 없는 사실, 판례, 절차 또는 결론을 만들지 마세요.
조문에 적힌 주체, 상대방, 조건, 시점, 금액, 배액 및 예외를 바꾸거나 생략하지 마세요.
서로 다른 조문의 법적 효과를 하나의 결론으로 혼합하지 마세요.
근거가 질문의 일부에만 답할 수 있다면 확인되는 범위만 설명하세요.
법률 자문이나 확정적인 판단처럼 표현하지 말고, 일반적인 법률 정보로 설명하세요.
답변에 사용한 근거의 documentId만 citedDocumentIds에 포함하세요.
답변의 핵심 설명 뒤에는 근거 documentId를 대괄호로 표시하세요. 예: [573]
충분한 근거가 없으면 answer는 null, citedDocumentIds는 빈 배열, status는 insufficient_evidence로 반환하세요.
충분한 근거가 있으면 status는 answered로 반환하세요."""


def build_legal_answer_messages(
  question: str,
  sources: list[dict[str, Any]],
) -> list[dict[str, str]]:
  selected_sources = sources[:MAX_ANSWER_SOURCES]
  context = [
    {
      "documentId": source["documentId"],
      "lawName": source["lawName"],
      "articleNo": source["articleNo"],
      "articleTitle": source.get("articleTitle"),
      "paragraphNo": source.get("paragraphNo", ""),
      "content": str(source["content"])[:MAX_SOURCE_CONTENT_CHARS],
    }
    for source in selected_sources
  ]
  user_prompt = "\n".join([
    f"사용자 질문: {question}",
    "검색된 법령 근거:",
    json.dumps(context, ensure_ascii=False, indent=2),
    "위 근거만 사용하여 한국어로 간결하고 이해하기 쉽게 답변하세요.",
  ])
  return [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": user_prompt},
  ]
