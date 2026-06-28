from __future__ import annotations

import json
import logging
import os
from typing import Annotated, Any, Callable

from fastapi import Depends
from openai import OpenAI


DEFAULT_CHAT_MODEL = "gpt-4o-mini"

RECOMMENDATION_SYSTEM_PROMPT = """
너는 부동산 추천 결과를 설명하는 RAG 답변 생성기다.

반드시 지켜야 할 원칙:
1. 제공된 criteria와 results 데이터만 근거로 답변한다.
2. 데이터에 없는 학군 평판, 교통 혼잡도, 미래 가격 전망은 추측하지 않는다.
3. 주변 인프라는 results 안의 matchedPois, infrastructure.nearestStation,
   infrastructure.nearestEducation, infrastructure.nearbyLifestyle 정보만 사용한다.
   생활편의는 800m 이내 백화점, 대형마트, 병원 POI만 근거로 설명한다.
4. 재개발/재건축/정비사업은 redevelopmentInfo의 웹검색 제목, 요약, URL만 근거로 소개한다.
5. 가격은 latestDealAmountText가 있으면 그대로 사용한다.
   latestDealAmount만 있으면 단위는 반드시 "만원"으로 해석한다.
   예: 330000은 330,000만원 = 33억원, 400000은 40억원이다.
6. 추천 이유는 사용자의 조건과 직접 연결해서 설명한다.
7. 후보가 여러 개면 가장 적합한 후보 1~3개를 우선순위로 제시하고, 왜 그렇게 판단했는지 말한다.
8. 조건에 맞는 후보가 없으면 없는 이유를 criteria와 results 기준으로 설명하고, 조건 완화 방향을 제안한다.
9. 모르는 내용은 "제공된 데이터만으로는 확인할 수 없습니다"라고 말한다.
10. 답변은 한국어로 작성하고, 과장된 투자 조언이나 확정적 표현은 피한다.
11. 마지막에는 "근거 데이터"를 짧게 요약한다.

좋은 답변 형식:
- 한 줄 결론
- 추천 후보와 이유
- 주요 인프라 근거
- 주의사항 또는 조건 완화 제안
- 근거 데이터 요약
""".strip()


class RecommendationRagAnswerAgent:
  # 추천 feature 전용 RAG 답변 생성기다.
  # 추천 서비스는 조회 결과를 만들고, 이 클래스는 그 결과를 한국어 답변으로 바꾼다.
  def __init__(self) -> None:
    self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

  def run(
    self,
    *,
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


RecommendationRagAnswerAgentDep = Annotated[
  RecommendationRagAnswerAgent,
  Depends(RecommendationRagAnswerAgent),
]


def generate_recommendation_answer(
  *,
  question: str,
  criteria: dict[str, Any],
  results: list[dict[str, Any]],
) -> str:
  if os.getenv("CHATBOT_USE_LLM_RAG_ANSWERS") != "1":
    return fallback_recommendation_answer(criteria, results)

  # 기존 service에서는 함수 하나만 호출하면 되도록 얇은 wrapper를 둔다.
  return RecommendationRagAnswerAgent().run(
    question=question,
    criteria=criteria,
    results=results,
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
      "nearbyLifestyle": infrastructure.get("nearbyLifestyle", []),
      "redevelopmentInfo": item.get("redevelopmentInfo", []),
      "notes": infrastructure.get("notes", []),
    })
  return compacted


def fallback_recommendation_answer(
  criteria: dict[str, Any],
  results: list[dict[str, Any]],
) -> str:
  if not results:
    if criteria:
      return "조건에 맞는 아파트를 찾지 못했습니다. 가격, 지역, 역/학교 반경 같은 조건을 조금 완화해 보세요."
    return "추천에 사용할 조건이나 조회 결과가 부족합니다. 지역, 가격, 세대수, 학교 같은 조건을 함께 입력해 주세요."

  top_items = results[:3]
  lines = ["조회된 데이터 기준으로는 다음 후보를 우선 검토할 수 있습니다."]
  for index, item in enumerate(top_items, start=1):
    name = item.get("complexName", "이름 미상")
    price = item.get("latestDealAmountText") or format_price(item.get("latestDealAmount"))
    station = format_poi(item.get("infrastructure", {}).get("nearestStation"))
    education = format_poi(item.get("infrastructure", {}).get("nearestEducation"))
    lifestyle = format_poi_list(item.get("infrastructure", {}).get("nearbyLifestyle", []))
    redevelopment = format_search_results(item.get("redevelopmentInfo", []))
    reasons = [f"최근 거래가 {price}"]
    if station:
      reasons.append(f"가까운 역 {station}")
    if education:
      reasons.append(f"가까운 교육시설 {education}")
    if lifestyle:
      reasons.append(f"800m 생활편의 {lifestyle}")
    if redevelopment:
      reasons.append(f"재개발/정비사업 검색결과 {redevelopment}")
    if item.get("unitCnt") is not None:
      reasons.append(f"{item['unitCnt']}세대")
    if item.get("useDate"):
      reasons.append(f"사용승인일 {item['useDate']}")
    lines.append(f"{index}. {name}: " + ", ".join(reasons))

  if has_search_results(results):
    lines.append("학군은 평판이 아니라 가까운 교육시설 거리 기준이며, 미래 가격은 예측하지 않고 웹검색된 재개발/정비사업 공개 정보만 참고로 제시했습니다.")
  else:
    lines.append("학군은 평판이 아니라 가까운 교육시설 거리 기준이며, 생활편의는 800m 이내 DB POI 기준으로만 제시했습니다.")
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


def format_poi_list(values: Any) -> str | None:
  if not isinstance(values, list) or not values:
    return None
  formatted = [format_lifestyle_poi(value) for value in values[:4]]
  formatted = [value for value in formatted if value]
  return ", ".join(formatted) if formatted else None


def format_lifestyle_poi(value: Any) -> str | None:
  if not isinstance(value, dict):
    return None
  name = value.get("name")
  distance = value.get("distanceM")
  subtype = value.get("subtype")
  if name is None or distance is None:
    return None
  label = f"{name}({round(float(distance))}m"
  if subtype:
    label += f", {subtype}"
  return f"{label})"


def format_search_results(values: Any) -> str | None:
  if not isinstance(values, list) or not values:
    return None
  titles = [
    str(value.get("title")).strip()
    for value in values[:2]
    if isinstance(value, dict) and value.get("title")
  ]
  return " / ".join(titles) if titles else None


def has_search_results(results: list[dict[str, Any]]) -> bool:
  return any(item.get("redevelopmentInfo") for item in results)
