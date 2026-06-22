from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI


DEFAULT_CHAT_MODEL = "gpt-4o-mini"

RECOMMENDATION_SYSTEM_PROMPT = """
너는 부동산 추천 결과를 설명하는 RAG 답변 생성기다.

반드시 지켜야 할 원칙:
1. 제공된 criteria와 results 데이터만 근거로 답변한다.
2. 데이터에 없는 상권, 학군 수준, 교통 편의, 호재, 미래 가격 전망은 추측하지 않는다.
3. 주변 인프라는 results 안의 matchedPois, infrastructure.nearestStation,
   infrastructure.nearestEducation 정보만 사용한다.
4. 가격은 latestDealAmountText가 있으면 그 값을 그대로 사용한다.
   latestDealAmount만 있으면 단위는 반드시 "만원"으로 해석한다.
   예: 330000은 330,000만원 = 33억 원, 400000은 40억 원이다.
5. 추천 이유는 사용자의 조건과 직접 연결해서 설명한다.
6. 후보가 여러 개면 가장 적합한 후보 1~3개를 우선순위로 제시하고, 왜 그렇게 판단했는지 말한다.
7. 조건에 맞는 후보가 없으면 없는 이유를 criteria와 results 기준으로 설명하고, 조건 완화 방향을 제안한다.
8. 모르는 내용은 "제공된 데이터만으로는 확인할 수 없습니다"라고 말한다.
9. 답변은 한국어로 작성하고, 과장된 투자 조언이나 확정적 표현을 피한다.
10. 마지막에는 "근거 데이터"를 짧게 요약한다.

좋은 답변 형식:
- 한 줄 결론
- 추천 후보와 이유
- 주변 인프라 근거
- 주의할 점 또는 조건 완화 제안
- 근거 데이터 요약
""".strip()

COMPARISON_SYSTEM_PROMPT = """
너는 아파트 비교 결과를 설명하는 RAG 답변 생성기다.

반드시 지켜야 할 원칙:
1. 제공된 criteria와 results 데이터만 근거로 비교한다.
2. 데이터에 없는 학군 평판, 상권 규모, 호재, 미래 가격 전망, 투자 수익률은 추측하지 않는다.
3. 가격은 latestDealAmountText가 있으면 그 값을 그대로 사용한다.
   latestDealAmount만 있으면 단위는 반드시 "만원"으로 해석한다.
4. 교통 비교는 nearestStation의 역 이름과 distanceM만 근거로 한다.
5. 교육 비교는 nearestSchool의 학교 이름, subtype, distanceM만 근거로 한다.
6. 상권/생활편의 데이터가 없다는 notes가 있으면, 상권은 판단하지 말고 데이터 부재를 명확히 말한다.
7. 어느 단지가 "무조건 더 좋다"고 단정하지 않는다. 사용자의 우선순위별로 유리한 쪽을 나눠 말한다.
8. 결과에 missingApartmentNames가 있으면 찾지 못한 단지를 먼저 알려준다.
9. 답변은 한국어로 작성하고, 간결하지만 비교 이유는 구체적으로 쓴다.
10. 마지막에는 "비교 근거"를 짧게 요약한다.

좋은 답변 형식:
- 한 줄 결론
- 항목별 비교: 가격, 규모/연식, 교통, 교육
- 사용자 우선순위별 선택 제안
- 데이터로 확인할 수 없는 부분
- 비교 근거 요약
""".strip()


def generate_rag_answer(
  *,
  question: str,
  intent: str,
  criteria: dict[str, Any],
  results: list[dict[str, Any]],
  extra: dict[str, Any] | None = None,
) -> str:
  extra = extra or {}
  if intent == "comparison":
    return generate_comparison_answer(question, criteria, results, extra)
  return generate_recommendation_answer(question, criteria, results)


def generate_recommendation_answer(
  question: str,
  criteria: dict[str, Any],
  results: list[dict[str, Any]],
) -> str:
  return generate_llm_answer(
    prompt=RECOMMENDATION_SYSTEM_PROMPT,
    user_instruction="아래 JSON 데이터를 근거로 사용자에게 최적의 아파트 추천 답변을 작성해줘.",
    context={
      "question": question,
      "intent": "recommendation",
      "criteria": criteria,
      "results": compact_recommendation_results(results[:5]),
    },
    fallback=lambda: fallback_recommendation_answer(criteria, results),
  )


def generate_comparison_answer(
  question: str,
  criteria: dict[str, Any],
  results: list[dict[str, Any]],
  extra: dict[str, Any],
) -> str:
  return generate_llm_answer(
    prompt=COMPARISON_SYSTEM_PROMPT,
    user_instruction="아래 JSON 데이터를 근거로 아파트 비교 답변을 작성해줘.",
    context={
      "question": question,
      "intent": "comparison",
      "criteria": criteria,
      "missingApartmentNames": extra.get("missingApartmentNames", []),
      "results": compact_comparison_results(results),
    },
    fallback=lambda: fallback_comparison_answer(criteria, results, extra.get("missingApartmentNames", [])),
  )


def generate_llm_answer(
  *,
  prompt: str,
  user_instruction: str,
  context: dict[str, Any],
  fallback,
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


def compact_recommendation_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
  compacted = []
  for item in results:
    infrastructure = item.get("infrastructure", {})
    compacted.append({
      "complexName": item.get("complexName"),
      "address": item.get("address"),
      "unitCnt": item.get("unitCnt"),
      "useDate": item.get("useDate"),
      "latestDealAmount": item.get("latestDealAmount"),
      "latestDealAmountText": item.get("latestDealAmountText") or format_price(item.get("latestDealAmount")),
      "latestDealDate": item.get("latestDealDate"),
      "pyeong": item.get("pyeong"),
      "nearestStation": infrastructure.get("nearestStation"),
      "nearestEducation": infrastructure.get("nearestEducation"),
      "nearestEducationByType": infrastructure.get("nearestEducationByType"),
      "educationDistanceTotalM": infrastructure.get("educationDistanceTotalM"),
      "notes": infrastructure.get("notes", []),
    })
  return compacted


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


def fallback_recommendation_answer(
  criteria: dict[str, Any],
  results: list[dict[str, Any]],
) -> str:
  if not results:
    if criteria:
      return "조건에 맞는 아파트를 찾지 못했습니다. 가격, 지역, 역/학교 반경 같은 조건을 조금 완화해 보세요."
    return "추천에 사용할 조건이나 조회 결과가 부족합니다. 지역, 가격, 역세권, 학교 같은 조건을 함께 입력해 주세요."

  top_items = results[:3]
  lines = ["조회된 데이터 기준으로는 다음 후보를 우선 검토할 수 있습니다."]
  for index, item in enumerate(top_items, start=1):
    name = item.get("complexName", "이름 미상")
    price = item.get("latestDealAmountText") or format_price(item.get("latestDealAmount"))
    station = format_poi(item.get("infrastructure", {}).get("nearestStation"))
    education = format_poi(item.get("infrastructure", {}).get("nearestEducation"))
    reasons = [f"최근 거래가 {price}"]
    if station:
      reasons.append(f"가까운 역 {station}")
    if education:
      reasons.append(f"가까운 교육시설 {education}")
    if item.get("unitCnt") is not None:
      reasons.append(f"{item['unitCnt']}세대")
    if item.get("useDate"):
      reasons.append(f"사용승인일 {item['useDate']}")
    lines.append(f"{index}. {name}: " + ", ".join(reasons))

  lines.append("제공된 데이터만으로 작성한 요약이며, 상권이나 학군 평판처럼 데이터에 없는 내용은 판단하지 않았습니다.")
  return "\n".join(lines)


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
    return f"{amount / 10000:.1f}억 원"
  return f"{int(amount):,}만 원"


def format_poi(value: Any) -> str | None:
  if not isinstance(value, dict):
    return None
  name = value.get("name")
  distance = value.get("distanceM")
  if name is None or distance is None:
    return None
  return f"{name}({round(float(distance))}m)"
