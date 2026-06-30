from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Literal


PlanType = Literal[
  "single_feature",
  "independent_multi_feature",
  "dependent_multi_feature",
  "ambiguous_multi_feature",
  "same_tool_multi_feature",
  "supported_unsupported_multi_feature",
  "unsupported_feature",
  "supervisor_llm",
]
StepMode = Literal["direct", "dependent", "ambiguous", "llm"]


@dataclass(frozen=True)
class FeatureStep:
  agent: str
  handler: str
  mode: StepMode = "direct"
  depends_on: str | None = None
  slot_overrides: dict[str, Any] = field(default_factory=dict)
  query: str | None = None


@dataclass(frozen=True)
class ExecutionPlan:
  plan_type: PlanType
  steps: list[FeatureStep] = field(default_factory=list)
  reason: str = ""


RECOMMENDATION_SIGNALS = ("추천", "권해", "골라", "조건에 맞는")
COMPARISON_SIGNALS = ("비교", "차이", "둘 중", "어디가 더", " vs ", "vs")
DEPENDENCY_SIGNALS = (
  "후보 비교",
  "후보들 비교",
  "추천 후보",
  "추천 결과 비교",
  "추천한 다음 비교",
  "추천하고 비교",
  "추천하고 후보 비교",
)
LOOKUP_ONLY_SIGNALS = (
  "위치",
  "주소",
  "최근 실거래",
  "실거래",
  "실거래가",
  "거래내역",
  "거래 내역",
  "최근 거래",
  "최고가",
  "최저가",
)
TREND_ONLY_SIGNALS = (
  "시세 추이",
  "시세추이",
  "시세 흐름",
  "가격 추이",
  "가격 흐름",
  "가격 변화",
  "변화",
  "변동률",
  "상승률",
  "하락률",
  "오른",
  "내린",
)
AMBIGUOUS_PRICE_SIGNALS = ("시세", "가격", "얼마")
LEGAL_SIGNALS = (
  "계약",
  "계약서",
  "매매계약",
  "법",
  "법령",
  "법률",
  "임대차",
  "전세",
  "세입자",
  "보증금",
  "세금",
  "명의",
  "등기",
  "등기부",
  "거래 신고",
  "신고해야",
  "신고필증",
  "허가",
  "토지거래허가",
  "소유권",
  "구분소유",
  "집합건물",
  "공인중개사",
  "매도인",
  "매매",
  "매매대금",
  "권리",
  "보태주",
  "증여",
  "계약금",
  "해제",
  "위약금",
)
UNSUPPORTED_SIGNALS = ("날씨", "주식", "환율", "서울 아파트", "부동산 후보", "근처 학교", "신고가", "신저가")
REGION_PATTERN = re.compile(r"강남\s*3구|강남삼구|강남3구|강남구|서초구|송파구|강남|서초|송파")


AGENT_BY_HANDLER = {
  "simple_lookup": "lookup_agent",
  "price_trend": "price_trend_agent",
  "recommendation": "recommendation_agent",
  "comparison": "comparison_agent",
  "legal_contract": "legal_contract_agent",
}


SUPPORTED_INDEPENDENT_COMBINATIONS = {
  frozenset(("recommendation", "legal_contract")),
  frozenset(("recommendation", "price_trend")),
  frozenset(("recommendation", "simple_lookup")),
  frozenset(("comparison", "legal_contract")),
  frozenset(("simple_lookup", "legal_contract")),
  frozenset(("price_trend", "legal_contract")),
}


def build_execution_plan(text: str) -> ExecutionPlan:
  question = normalize_text(text)
  if not question:
    return supervisor_plan("empty_question")

  nearby_comparison_plan = build_nearby_candidate_comparison_plan(question)
  if nearby_comparison_plan is not None:
    return nearby_comparison_plan

  dependent_plan = build_dependent_multi_feature_plan(question)
  if dependent_plan is not None:
    return dependent_plan

  if looks_like_unsupported_dependent_chain(question):
    return supervisor_plan("unsupported_dependent_chain")

  same_tool_plan = build_same_tool_multi_feature_plan(question)
  if same_tool_plan is not None:
    return same_tool_plan

  if looks_like_same_tool_multi_target(question):
    return supervisor_plan("same_tool_multi_target")

  supported_unsupported_plan = build_supported_unsupported_multi_feature_plan(question)
  if supported_unsupported_plan is not None:
    return supported_unsupported_plan

  unsupported_plan = build_unsupported_feature_plan(question)
  if unsupported_plan is not None:
    return unsupported_plan

  ambiguous_plan = build_ambiguous_multi_feature_plan(question)
  if ambiguous_plan is not None:
    return ambiguous_plan

  independent_plan = build_independent_multi_feature_plan(question)
  if independent_plan is not None:
    return independent_plan

  single_plan = build_single_feature_plan(question)
  if single_plan is not None:
    return single_plan

  return supervisor_plan("no_deterministic_rule")


def build_dependent_multi_feature_plan(text: str) -> ExecutionPlan | None:
  if not has_recommendation_signal(text):
    return None
  if not has_comparison_signal(text):
    return None
  if not has_dependency_signal(text):
    return None

  return ExecutionPlan(
    plan_type="dependent_multi_feature",
    steps=[
      FeatureStep(
        agent="recommendation_agent",
        handler="recommendation",
        mode="direct",
      ),
      FeatureStep(
        agent="comparison_agent",
        handler="comparison",
        mode="dependent",
        depends_on="recommendation_agent",
      ),
    ],
    reason="recommendation_candidates_feed_comparison",
  )


def build_nearby_candidate_comparison_plan(text: str) -> ExecutionPlan | None:
  if not has_comparison_signal(text):
    return None
  if "아파트" not in text:
    return None
  if re.search(
    r"(?:[가-힣A-Za-z0-9()]+역|[가-힣A-Za-z0-9]+(?:유치원|초등학교|중학교|고등학교|특수학교|초|중|고))"
    r"\s*(?:이랑|랑|와|과|에서)?\s*(?:가까운|가까이에|근처|주변|인근)",
    text,
  ) is None:
    return None

  return ExecutionPlan(
    plan_type="dependent_multi_feature",
    steps=[
      FeatureStep(
        agent="recommendation_agent",
        handler="recommendation",
        mode="direct",
      ),
      FeatureStep(
        agent="comparison_agent",
        handler="comparison",
        mode="dependent",
        depends_on="recommendation_agent",
      ),
    ],
    reason="nearby_candidates_feed_comparison",
  )


def has_dependency_signal(text: str) -> bool:
  if any(signal in text for signal in DEPENDENCY_SIGNALS):
    return True
  return re.search(r"후보(?:\s*\d+\s*(?:개|곳|건))?\s*비교", text) is not None


def looks_like_unsupported_dependent_chain(text: str) -> bool:
  return (
    has_recommendation_signal(text)
    and (has_price_trend_signal(text) or has_simple_lookup_signal(text))
    and any(signal in text for signal in (
      "추천 후보",
      "추천한 단지",
      "추천 결과",
      "후보들",
      "후보의",
      "후보 실거래",
      "후보 위치",
      "후보 가격",
      "후보들 가격",
    ))
  )


def looks_like_same_tool_multi_target(text: str) -> bool:
  if has_comparison_signal(text):
    return False
  if not (has_price_trend_signal(text) or any(signal in text for signal in AMBIGUOUS_PRICE_SIGNALS)):
    return False
  regions = distinct_region_names(text)
  if len(regions) > 1:
    return True
  return len(distinct_complex_names_for_trend(text)) > 1


def build_same_tool_multi_feature_plan(text: str) -> ExecutionPlan | None:
  if not has_price_trend_signal(text):
    return None

  targets = price_trend_multi_targets(text)
  if len(targets) < 2:
    return None

  return ExecutionPlan(
    plan_type="same_tool_multi_feature",
    steps=[
      FeatureStep(
        agent="price_trend_agent",
        handler="price_trend",
        mode="direct",
        query=f"{target_name} 시세 추이 알려줘",
        slot_overrides={
          "analysis_type": "timeseries",
          "target_type": target_type,
          "target_name": target_name,
          "period": "1y",
        },
      )
      for target_type, target_name in targets
    ],
    reason="same_tool_multiple_targets",
  )


def price_trend_multi_targets(text: str) -> list[tuple[str, str]]:
  regions = distinct_region_names(text)
  if len(regions) > 1:
    return [("region", region) for region in regions]

  complexes = distinct_complex_names_for_trend(text)
  if len(complexes) > 1:
    return [("complex", complex_name) for complex_name in complexes]

  return []


def build_supported_unsupported_multi_feature_plan(text: str) -> ExecutionPlan | None:
  if not any(signal in text for signal in UNSUPPORTED_SIGNALS):
    return None

  handlers = detected_handlers(text)
  if not handlers:
    return None

  unsupported_query = clause_from_first_signal(text, UNSUPPORTED_SIGNALS)
  return ExecutionPlan(
    plan_type="supported_unsupported_multi_feature",
    steps=[
      *[
        step_for_handler(
          handler,
          text,
          mode="direct",
          query=sub_query_for_handler(handler, text),
        )
        for handler in handlers
      ],
      FeatureStep(
        agent="unsupported_agent",
        handler="no_matching_tool",
        mode="direct",
        query=unsupported_query,
      ),
    ],
    reason="supported_and_unsupported_question",
  )


def build_unsupported_feature_plan(text: str) -> ExecutionPlan | None:
  if not any(signal in text for signal in UNSUPPORTED_SIGNALS):
    return None
  if detected_handlers(text):
    return None

  return ExecutionPlan(
    plan_type="unsupported_feature",
    steps=[
      FeatureStep(
        agent="unsupported_agent",
        handler="no_matching_tool",
        mode="direct",
        query=text,
      ),
    ],
    reason="unsupported_question",
  )


def looks_like_supported_unsupported_mixed_question(text: str) -> bool:
  if not any(signal in text for signal in UNSUPPORTED_SIGNALS):
    return False
  return bool(detected_handlers(text))


def distinct_region_names(text: str) -> list[str]:
  names = []
  for match in REGION_PATTERN.finditer(text):
    name = re.sub(r"\s+", "", match.group(0))
    aliases = {
      "강남": "강남구",
      "서초": "서초구",
      "송파": "송파구",
      "강남삼구": "강남3구",
    }
    normalized = aliases.get(name, name)
    if normalized not in names:
      names.append(normalized)
  return names


def distinct_complex_names_for_trend(text: str) -> list[str]:
  target_text = extract_entity_before_keywords(
    text,
    TREND_ONLY_SIGNALS + ("시세", "가격"),
    reject_region=False,
  )
  if not target_text:
    return []
  if looks_like_region_target(target_text):
    return []

  names = []
  for candidate in re.split(r"\s*(?:,|/|랑|와|과|하고)\s*", target_text):
    name = clean_target_candidate(candidate)
    if not name or looks_like_region_target(name):
      continue
    if name not in names:
      names.append(name)
  return names


def build_ambiguous_multi_feature_plan(text: str) -> ExecutionPlan | None:
  if not looks_like_ambiguous_complex_price_question(text):
    return None

  target_name = extract_complex_target_name(text)
  if not target_name:
    return None

  return ExecutionPlan(
    plan_type="ambiguous_multi_feature",
    steps=[
      FeatureStep(
        agent="lookup_agent",
        handler="simple_lookup",
        mode="ambiguous",
        slot_overrides={
          "query_type": "trade_history",
          "target_name": target_name,
        },
      ),
      FeatureStep(
        agent="price_trend_agent",
        handler="price_trend",
        mode="ambiguous",
        slot_overrides={
          "analysis_type": "timeseries",
          "target_type": "complex",
          "target_name": target_name,
          "period": "1y",
        },
      ),
    ],
    reason="complex_price_question_needs_recent_trade_and_trend",
  )


def build_independent_multi_feature_plan(text: str) -> ExecutionPlan | None:
  handlers = detected_handlers(text)
  if len(handlers) < 2:
    return None

  handler_set = frozenset(handlers)
  if handler_set not in SUPPORTED_INDEPENDENT_COMBINATIONS:
    return None

  return ExecutionPlan(
    plan_type="independent_multi_feature",
    steps=[
      step_for_handler(
        handler,
        text,
        mode="direct",
        query=sub_query_for_handler(handler, text),
      )
      for handler in handlers
    ],
    reason="multiple_independent_evidence_domains",
  )


def build_single_feature_plan(text: str) -> ExecutionPlan | None:
  handlers = detected_handlers(text)
  if len(handlers) == 1:
    handler = handlers[0]
    return ExecutionPlan(
      plan_type="single_feature",
      steps=[step_for_handler(handler, text, mode="direct")],
      reason=f"single_{handler}",
    )
  return None


def step_for_handler(
  handler: str,
  text: str,
  mode: StepMode = "direct",
  query: str | None = None,
) -> FeatureStep:
  return FeatureStep(
    agent=AGENT_BY_HANDLER[handler],
    handler=handler,
    mode=mode,
    slot_overrides=slot_overrides_for_handler(handler, text),
    query=query,
  )


def slot_overrides_for_handler(handler: str, text: str) -> dict[str, Any]:
  if handler == "simple_lookup":
    return simple_lookup_slot_overrides(text)
  if handler == "price_trend":
    return price_trend_slot_overrides(text)
  return {}


def simple_lookup_slot_overrides(text: str) -> dict[str, Any]:
  overrides: dict[str, Any] = {}
  target_name = extract_lookup_target_name(text)
  if target_name:
    overrides["target_name"] = target_name
  if any(signal in text for signal in ("위치", "주소", "어디", "좌표")) or looks_like_find_location_question(text):
    overrides["query_type"] = "location"
  elif any(signal in text for signal in ("최고가", "가장 비싼", "제일 비싼")):
    overrides["query_type"] = "region_price_ranking" if looks_like_region_target(target_name or "") else "complex_price_record"
    overrides["price_order"] = "highest"
  elif any(signal in text for signal in ("최저가", "가장 싼", "제일 싼")):
    overrides["query_type"] = "region_price_ranking" if looks_like_region_target(target_name or "") else "complex_price_record"
    overrides["price_order"] = "lowest"
  elif any(signal in text for signal in ("실거래", "거래내역", "거래 내역", "최근 거래", "가격", "시세", "얼마")) or re.search(r"최근\s*\d+\s*건", text):
    overrides["query_type"] = "trade_history"
  if overrides.get("query_type") == "trade_history" and looks_like_region_target(str(overrides.get("target_name") or "")):
    overrides.pop("target_name", None)
  return overrides


def price_trend_slot_overrides(text: str) -> dict[str, Any]:
  if looks_like_ranking_price_trend_question(text):
    target_name = extract_region_name(text)
    if not target_name:
      return {}
    return {
      "target_type": "region",
      "target_name": target_name,
    }

  target_name = extract_region_name(text)
  target_type = "region" if target_name else "complex"
  if not target_name:
    target_name = extract_complex_target_name(text) or extract_lookup_target_name(text)

  overrides: dict[str, Any] = {
    "analysis_type": "timeseries",
    "target_type": target_type,
  }
  if target_name:
    overrides["target_name"] = target_name
  if "period" not in overrides and not any(re.search(pattern, text) for pattern in (r"(?:최근|지난)\s*\d+\s*(?:개월|달|년)", r"\d{4}\s*년")):
    overrides["period"] = "1y"
  return overrides


def detected_handlers(text: str) -> list[str]:
  candidates: list[tuple[int, str]] = []

  if has_recommendation_signal(text):
    candidates.append((signal_position(text, RECOMMENDATION_SIGNALS), "recommendation"))
  if has_comparison_signal(text):
    candidates.append((signal_position(text, COMPARISON_SIGNALS), "comparison"))
  if has_price_trend_signal(text):
    candidates.append((price_trend_position(text), "price_trend"))
  if has_simple_lookup_signal(text):
    candidates.append((simple_lookup_position(text), "simple_lookup"))
  if has_legal_signal(text):
    candidates.append((signal_position(text, LEGAL_SIGNALS), "legal_contract"))

  ordered = [
    handler
    for _, handler in sorted(candidates, key=lambda item: (item[0], item[1]))
  ]
  if "comparison" in ordered:
    ordered = [handler for handler in ordered if handler != "simple_lookup"]
  return dedupe_preserve_order(ordered)


def sub_query_for_handler(handler: str, text: str) -> str | None:
  if handler == "recommendation":
    return recommendation_sub_query(text)
  if handler == "comparison":
    return comparison_sub_query(text)
  if handler == "simple_lookup":
    return simple_lookup_sub_query(text)
  if handler == "price_trend":
    return price_trend_sub_query(text)
  if handler == "legal_contract":
    return clause_from_first_signal(text, LEGAL_SIGNALS)
  return None


def recommendation_sub_query(text: str) -> str | None:
  position = signal_position(text, RECOMMENDATION_SIGNALS)
  if position >= len(text):
    return None
  prefix = text[:position].strip()
  return f"{prefix} 추천해줘".strip()


def comparison_sub_query(text: str) -> str | None:
  position = signal_position(text, COMPARISON_SIGNALS)
  if position >= len(text):
    return None
  return f"{text[:position].strip()} 비교해줘".strip()


def simple_lookup_sub_query(text: str) -> str | None:
  overrides = simple_lookup_slot_overrides(text)
  target_name = overrides.get("target_name")
  query_type = overrides.get("query_type")
  if isinstance(target_name, str) and query_type == "location":
    return f"{target_name} 위치 알려줘"
  if isinstance(target_name, str) and query_type in {"trade_history", "complex_price_record"}:
    return f"{target_name} 최근 실거래 알려줘"
  if target_name is None and query_type in {"trade_history", "complex_price_record"}:
    return clause_from_first_signal(text, LOOKUP_ONLY_SIGNALS + ("가격", "시세", "얼마"))
  return clause_from_first_signal(text, LOOKUP_ONLY_SIGNALS + ("어디", "좌표", "가격", "얼마", "찾아"))


def price_trend_sub_query(text: str) -> str | None:
  clause = clause_from_first_signal(text, TREND_ONLY_SIGNALS + ("시세", "가격"))
  target = extract_region_name(text) or extract_complex_target_name(text)
  if target and clause and target not in clause:
    return f"{target} {clause}"
  return clause


def clause_from_first_signal(text: str, signals: tuple[str, ...]) -> str | None:
  signal_pos = signal_position(text, signals)
  if signal_pos >= len(text):
    return None
  start = last_connector_end_before(text, signal_pos)
  end = next_connector_start_after(text, signal_pos)
  clause = text[start:end].strip(" ,")
  return clause or None


def last_connector_end_before(text: str, position: int) -> int:
  prefix = text[:position]
  matches = list(re.finditer(r"(그리고|또|하고|랑|와|과)\s*", prefix))
  return matches[-1].end() if matches else 0


def next_connector_start_after(text: str, position: int) -> int:
  suffix = text[position:]
  match = re.search(r"\s+(?:그리고|또|하고)\s+", suffix)
  if match is None:
    return len(text)
  return position + match.start()


def has_recommendation_signal(text: str) -> bool:
  if any(signal in text for signal in RECOMMENDATION_SIGNALS):
    return True
  if has_price_trend_signal(text):
    return False
  if any(signal in text for signal in ("최고가", "최저가", "가장 비싼", "제일 비싼", "가장 싼", "제일 싼")):
    return False
  return re.search(
    r"(?:[가-힣A-Za-z0-9]+역|강남구|서초구|송파구|근처|주변|인근).*(?:아파트|단지)\s*(?:알려|보여)",
    text,
  ) is not None


def has_comparison_signal(text: str) -> bool:
  if any(signal in text for signal in COMPARISON_SIGNALS):
    return True
  return re.search(
    r".+(?:랑|와|과|하고).+(?:중\s*어디|어디가|더\s*가까|가까워|접근성)",
    text,
  ) is not None


def has_legal_signal(text: str) -> bool:
  if "신고가" in text or "신저가" in text:
    return False
  return any(signal in text for signal in LEGAL_SIGNALS)


def has_price_trend_signal(text: str) -> bool:
  if any(signal in text for signal in TREND_ONLY_SIGNALS):
    return True
  return is_region_price_question(text)


def has_simple_lookup_signal(text: str) -> bool:
  if has_legal_signal(text) and not any(signal in text for signal in LOOKUP_ONLY_SIGNALS):
    return False
  if any(signal in text for signal in LOOKUP_ONLY_SIGNALS):
    return True
  if looks_like_find_location_question(text):
    return True
  if any(signal in text for signal in ("가장 비싼", "제일 비싼", "가장 싼", "제일 싼", "제일 싸")):
    return True
  if re.search(r"최근\s*\d+\s*건", text):
    return True
  if any(signal in text for signal in ("어디", "좌표")):
    return True
  if any(signal in text for signal in ("가격", "얼마")) and not has_comparison_signal(text) and not has_price_trend_signal(text):
    return True
  return False


def looks_like_ambiguous_complex_price_question(text: str) -> bool:
  if not any(signal in text for signal in AMBIGUOUS_PRICE_SIGNALS):
    return False
  if any(signal in text for signal in LOOKUP_ONLY_SIGNALS):
    return False
  if any(signal in text for signal in TREND_ONLY_SIGNALS):
    return False
  if is_region_price_question(text):
    return False
  if has_recommendation_signal(text) or has_comparison_signal(text) or has_legal_signal(text):
    return False
  return bool(extract_complex_target_name(text))


def is_region_price_question(text: str) -> bool:
  return extract_region_name(text) is not None and any(signal in text for signal in ("시세", "가격", "추이", "흐름"))


def extract_region_name(text: str) -> str | None:
  match = REGION_PATTERN.search(text)
  if match is None:
    return None
  name = re.sub(r"\s+", "", match.group(0))
  aliases = {
    "강남": "강남구",
    "서초": "서초구",
    "송파": "송파구",
    "강남삼구": "강남3구",
  }
  return aliases.get(name, name)


def extract_complex_target_name(text: str) -> str | None:
  return extract_entity_before_keywords(
    text,
    ("시세", "가격", "얼마", "요즘", "최근"),
    reject_region=True,
  )


def extract_lookup_target_name(text: str) -> str | None:
  region = extract_region_name(text)
  if region and any(signal in text for signal in (
    "TOP",
    "top",
    "순위",
    "랭킹",
    "최고가",
    "최저가",
    "가장 비싼",
    "제일 비싼",
    "가장 싼",
    "제일 싼",
  )):
    return region

  target = extract_entity_before_keywords(
    text,
    (
      "위치",
      "주소",
      "어디",
      "좌표",
      "최근 실거래",
      "실거래가",
      "실거래",
      "거래내역",
      "거래 내역",
      "최근 거래",
      "최고가",
      "최저가",
      "가장 비싼",
      "제일 비싼",
      "가장 싼",
      "제일 싼",
      "가격",
      "시세",
      "얼마",
      "찾아",
    ),
    reject_region=False,
  )
  if target:
    return target

  target = extract_entity_before_keywords(
    text,
    ("최근",),
    reject_region=False,
  )
  if target:
    return target

  trailing_match = re.search(
    r"(?:최근\s*)?(?:실거래가?|거래내역|거래\s*내역|가격|시세)\s+(?P<target>.+?)\s*(?:알려|보여|조회|$)",
    text,
  )
  if trailing_match is not None:
    trailing_target = clean_target_candidate(trailing_match.group("target"))
    if trailing_target:
      return trailing_target

  return target or region


def extract_entity_before_keywords(text: str, keywords: tuple[str, ...], *, reject_region: bool) -> str | None:
  positions = [
    text.find(keyword)
    for keyword in keywords
    if text.find(keyword) > 0
  ]
  if not positions:
    return None
  candidate = text[:min(positions)]
  candidate = clean_target_candidate(candidate)
  if not candidate:
    return None
  if has_recommendation_signal(candidate):
    return None
  if reject_region and looks_like_region_target(candidate):
    return None
  return candidate


def clean_target_candidate(value: str) -> str:
  text = value
  text = re.sub(r"(?:최근|지난|요즘|현재|가장)\s*", "", text)
  text = re.sub(r"\d+\s*(?:개월|달|년|건)", "", text)
  text = re.sub(r"\d{4}\s*년", "", text)
  text = re.sub(r"\d+(?:\.\d+)?\s*(?:평|평형|㎡|m2|제곱미터)", "", text, flags=re.IGNORECASE)
  text = re.sub(r"전용\s*", "", text)
  text = re.sub(r"\s+(?:아파트|단지)\s*$", "", text)
  text = re.sub(r"(?:그리고|또|랑|와|과|하고)\s*$", "", text)
  text = re.sub(r"(?:에서|부터)$", "", text)
  text = text.strip(" ,")
  text = re.sub(r"\s+", "", text)
  text = text.rstrip("은는이가을를")
  return text.strip()


def looks_like_find_location_question(text: str) -> bool:
  match = re.search(r"(?P<target>.+?)\s*찾아(?:줘|주세요)?\??$", text)
  if match is None:
    return False
  target = clean_target_candidate(match.group("target"))
  if not target or looks_like_region_target(target):
    return False
  return re.fullmatch(
    r"(?:강남구|서초구|송파구|강남|서초|송파)?(?:아파트|단지)",
    target,
  ) is None


def looks_like_region_target(value: str) -> bool:
  if not value:
    return False
  return extract_region_name(value) == re.sub(r"\s+", "", value) or value in {"강남", "서초", "송파"}


def looks_like_ranking_price_trend_question(text: str) -> bool:
  return re.search(
    r"많이\s*오른|상승률\s*높은|오른\s*아파트|많이\s*내린|하락률\s*높은|내린\s*아파트",
    text,
  ) is not None


def signal_position(text: str, signals: tuple[str, ...]) -> int:
  positions = [text.find(signal) for signal in signals if text.find(signal) >= 0]
  return min(positions) if positions else len(text)


def price_trend_position(text: str) -> int:
  return min(
    signal_position(text, TREND_ONLY_SIGNALS),
    signal_position(text, ("시세", "가격")),
  )


def simple_lookup_position(text: str) -> int:
  return signal_position(text, LOOKUP_ONLY_SIGNALS + ("어디", "좌표", "가격", "얼마", "찾아"))


def dedupe_preserve_order(values: list[str]) -> list[str]:
  result = []
  seen = set()
  for value in values:
    if value in seen:
      continue
    result.append(value)
    seen.add(value)
  return result


def normalize_text(text: str) -> str:
  return re.sub(r"\s+", " ", text.strip())


def supervisor_plan(reason: str) -> ExecutionPlan:
  return ExecutionPlan(
    plan_type="supervisor_llm",
    steps=[],
    reason=reason,
  )
