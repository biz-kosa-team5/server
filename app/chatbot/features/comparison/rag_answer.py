from __future__ import annotations

import json
import logging
import os
from typing import Annotated, Any, Callable

from fastapi import Depends
from openai import OpenAI


DEFAULT_CHAT_MODEL = "gpt-4o-mini"

COMPARISON_SYSTEM_PROMPT = """
너는 아파트 비교 결과를 설명하는 RAG 답변 생성기다.

반드시 지켜야 할 원칙:
1. 제공된 criteria와 results 데이터만 근거로 비교한다.
2. 데이터에 없는 학군 평판, 상권 규모, 호재, 미래 가격 전망, 투자 수익률은 추측하지 않는다.
3. 가격은 latestDealAmountText가 있으면 그대로 사용한다.
   latestDealAmount만 있으면 단위는 반드시 "만원"으로 해석한다.
4. 교통 비교는 nearestStation의 역 이름과 distanceM만 근거로 한다.
5. 교육 비교는 nearestSchool의 학교 이름, subtype, distanceM만 근거로 한다.
6. 상권/생활편의 데이터가 없다는 notes가 있으면 상권은 판단하지 말고 데이터 부족을 명확히 말한다.
7. 어느 단지가 무조건 더 좋다고 단정하지 말고, 사용자의 우선순위별로 유리한 쪽을 나누어 말한다.
8. 결과에 missingApartmentNames가 있으면 찾지 못한 단지를 먼저 알려준다.
9. 답변은 한국어로 작성하고, 간결하지만 비교 이유는 구체적으로 든다.
10. 마지막에는 "비교 근거"를 짧게 요약한다.

좋은 답변 형식:
- 한 줄 결론
- 항목별 비교: 가격, 규모/연식, 교통, 교육
- 사용자 우선순위별 선택 제안
- 데이터로 확인할 수 없는 부분
- 비교 근거 요약
""".strip()


class ComparisonRagAnswerAgent:
  # 비교 feature 전용 RAG 답변 생성기다.
  # 비교 서비스가 만든 rows와 missingApartmentNames를 사람이 읽을 답변으로 바꾼다.
  def __init__(self) -> None:
    self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

  def run(
    self,
    *,
    question: str,
    criteria: dict[str, Any],
    results: list[dict[str, Any]],
    missing_apartment_names: list[str] | None = None,
  ) -> str:
    missing_apartment_names = missing_apartment_names or []
    return generate_llm_answer(
      prompt=COMPARISON_SYSTEM_PROMPT,
      user_instruction="아래 JSON 데이터를 근거로 아파트 비교 답변을 작성해줘.",
      context={
        "question": question,
        "intent": "comparison",
        "criteria": criteria,
        "missingApartmentNames": missing_apartment_names,
        "results": compact_comparison_results(results),
      },
      fallback=lambda: fallback_comparison_answer(criteria, results, missing_apartment_names),
    )


ComparisonRagAnswerAgentDep = Annotated[
  ComparisonRagAnswerAgent,
  Depends(ComparisonRagAnswerAgent),
]


def generate_comparison_answer(
  *,
  question: str,
  criteria: dict[str, Any],
  results: list[dict[str, Any]],
  missing_apartment_names: list[str] | None = None,
) -> str:
  if os.getenv("CHATBOT_USE_LLM_RAG_ANSWERS") != "1":
    return fallback_comparison_answer(criteria, results, missing_apartment_names or [])

  # 기존 service에서는 함수 하나만 호출하면 되도록 얇은 wrapper를 둔다.
  return ComparisonRagAnswerAgent().run(
    question=question,
    criteria=criteria,
    results=results,
    missing_apartment_names=missing_apartment_names,
  )


def generate_llm_answer(
  *,
  prompt: str,
  user_instruction: str,
  context: dict[str, Any],
  fallback: Callable[[], str],
) -> str:
  api_key = os.getenv("OPENAI_API_KEY")
  if not api_key:
    return fallback()

  try:
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
      model=os.getenv("OPENAI_CHAT_MODEL", DEFAULT_CHAT_MODEL),
      temperature=0.2,
      messages=[
        {"role": "system", "content": prompt},
        {
          "role": "user",
          "content": (
            f"{user_instruction}\n"
            f"{json.dumps(context, ensure_ascii=False, indent=2)}"
          ),
        },
      ],
    )
  except Exception:
    return fallback()

  answer = response.choices[0].message.content
  return answer.strip() if answer else fallback()


def compact_comparison_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
  return [
    {
      "complexName": item.get("complexName"),
      "latestDealAmount": item.get("latestDealAmount"),
      "latestDealAmountText": item.get("latestDealAmountText") or format_price(item.get("latestDealAmount")),
      "pyeong": item.get("pyeong"),
      "pricePerPyeong": item.get("pricePerPyeong"),
      "pricePerPyeongText": format_price(item.get("pricePerPyeong")),
      "unitCnt": item.get("unitCnt"),
      "builtYear": item.get("builtYear"),
      "nearestStation": item.get("nearestStation"),
      "nearestSchool": item.get("nearestSchool"),
      "infrastructureNotes": item.get("infrastructureNotes", []),
    }
    for item in results
  ]


def fallback_comparison_answer(
  criteria: dict[str, Any],
  results: list[dict[str, Any]],
  missing_names: list[str],
) -> str:
  if missing_names:
    return f"일부 아파트를 찾지 못했습니다: {', '.join(map(str, missing_names))}"
  if len(results) < 2:
    return "비교할 아파트 데이터가 부족합니다. 아파트명을 2개 이상 입력해 주세요."

  lines = ["조회된 데이터 기준으로 비교하면 다음과 같습니다."]
  for item in results:
    name = item.get("complexName", "이름 미상")
    price = item.get("latestDealAmountText") or format_price(item.get("latestDealAmount"))
    station = format_poi(item.get("nearestStation"))
    school = format_poi(item.get("nearestSchool"))
    parts = [f"최근 거래가 {price}"]
    if item.get("unitCnt") is not None:
      parts.append(f"{item['unitCnt']}세대")
    if item.get("builtYear") is not None:
      parts.append(f"{item['builtYear']}년 준공")
    if station:
      parts.append(f"가까운 역 {station}")
    if school:
      parts.append(f"가까운 학교 {school}")
    lines.append(f"- {name}: " + ", ".join(parts))
  lines.append("상권, 학군 평판, 미래 가격 전망은 제공된 데이터만으로는 확인할 수 없습니다.")
  return "\n".join(lines)


def format_price(value: Any) -> str:
  if value is None:
    return "정보 없음"
  amount = float(value)
  if amount >= 10000:
    return f"{amount / 10000:.1f}억원"
  return f"{int(amount):,}만원"


def format_poi(value: Any) -> str | None:
  if not isinstance(value, dict):
    return None
  name = value.get("name")
  distance = value.get("distanceM")
  if name is None or distance is None:
    return None
  return f"{name}({round(float(distance))}m)"
