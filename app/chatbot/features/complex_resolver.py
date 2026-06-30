from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
import math
import re
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Complex


RESOLVED = "resolved"
AMBIGUOUS = "ambiguous"
NOT_FOUND = "not_found"
INSUFFICIENT_QUERY = "insufficient_query"

GENERIC_SUFFIXES = ("아파트", "단지", "apt")
GENERIC_CORE_NAMES = {
  "",
  "아파트",
  "단지",
  "apt",
  "아파트단지",
  "그냥",
  "아무",
  "아무거나",
  "어디",
}
QUERY_ACTION_SUFFIXES = (
  "찾아줘",
  "알려줘",
  "보여줘",
  "조회해줘",
  "추천해줘",
  "해줘",
  "줘",
)
PARTICLE_SUFFIXES = ("으로", "로", "은", "는", "이", "가", "을", "를")
DISTANCE_CONTEXT_LIMIT_M = 4000.0


@dataclass(frozen=True)
class ComplexResolverContext:
  region_id: int | None = None
  region_name: str | None = None
  address_keywords: tuple[str, ...] = ()
  anchor_complex: Complex | None = None
  auto_resolve_with_context: bool = True


@dataclass(frozen=True)
class ComplexResolution:
  status: str
  query: str
  variants: list[str] = field(default_factory=list)
  complex: Complex | None = None
  candidates: list[dict[str, Any]] = field(default_factory=list)
  message: str = ""
  resolution_notes: list[str] = field(default_factory=list)

  @property
  def resolved(self) -> bool:
    return self.status == RESOLVED and self.complex is not None


@dataclass(frozen=True)
class CandidateScore:
  row: Complex
  score: int
  match_reason: str
  matched_variant: str


class ComplexResolver:
  def __init__(self, session: Session, *, search_limit: int = 50) -> None:
    self.session = session
    self.search_limit = search_limit

  def resolve(
    self,
    query: str,
    context: ComplexResolverContext | None = None,
  ) -> ComplexResolution:
    query_text = clean_query_text(query)
    variants = complex_name_variants(query_text)

    if is_insufficient_complex_query(query_text, variants):
      return ComplexResolution(
        status=INSUFFICIENT_QUERY,
        query=query_text,
        variants=variants,
        message="조회할 단지명이 부족합니다. 지역이나 단지명을 더 구체적으로 알려주세요.",
      )

    scored = self._find_candidates(variants, context or ComplexResolverContext())
    if not scored:
      return ComplexResolution(
        status=NOT_FOUND,
        query=query_text,
        variants=variants,
        message="조회 대상 단지를 찾을 수 없습니다.",
      )

    candidates = [candidate_to_dict(item) for item in scored]
    if len(scored) == 1:
      return ComplexResolution(
        status=RESOLVED,
        query=query_text,
        variants=variants,
        complex=scored[0].row,
        candidates=candidates[:1],
        message="단지를 확인했습니다.",
      )

    context = context or ComplexResolverContext()
    if should_auto_resolve(scored, query_text, context):
      note = resolution_note(scored[0], query_text, context)
      return ComplexResolution(
        status=RESOLVED,
        query=query_text,
        variants=variants,
        complex=scored[0].row,
        candidates=candidates,
        message="문맥에 가장 가까운 단지를 기준으로 확인했습니다.",
        resolution_notes=[note] if note else [],
      )

    return ComplexResolution(
      status=AMBIGUOUS,
      query=query_text,
      variants=variants,
      candidates=candidates,
      message="여러 단지가 검색되었습니다. 더 구체적으로 입력해주세요.",
    )

  def _find_candidates(
    self,
    variants: list[str],
    context: ComplexResolverContext,
  ) -> list[CandidateScore]:
    rows = self._query_rows(variants)
    scored = [
      score_complex_candidate(row, variants, context)
      for row in rows
    ]
    scored = [item for item in scored if item.score > 0]
    scored.sort(key=lambda item: (-item.score, -(item.row.unit_cnt or 0), item.row.name, item.row.id))
    return scored[:self.search_limit]

  def _query_rows(self, variants: list[str]) -> list[Complex]:
    if not variants:
      return []

    name_expr = normalized_sql_text(Complex.name)
    trade_name_expr = normalized_sql_text(func.coalesce(Complex.trade_name, ""))

    exact_conditions = []
    partial_conditions = []
    for variant in variants:
      if len(variant) < 2:
        continue
      exact_conditions.extend([name_expr == variant, trade_name_expr == variant])
      partial_conditions.extend([name_expr.like(f"%{variant}%"), trade_name_expr.like(f"%{variant}%")])

    if not exact_conditions and not partial_conditions:
      return []

    rows: dict[int, Complex] = {}
    if exact_conditions:
      for row in self.session.scalars(
        select(Complex)
        .where(or_(*exact_conditions))
        .order_by(Complex.name.asc(), Complex.id.asc())
        .limit(self.search_limit)
      ).all():
        rows[row.id] = row

    if partial_conditions and len(rows) < self.search_limit:
      for row in self.session.scalars(
        select(Complex)
        .where(or_(*partial_conditions))
        .order_by(Complex.name.asc(), Complex.id.asc())
        .limit(self.search_limit)
      ).all():
        rows[row.id] = row

    return list(rows.values())


def normalized_sql_text(column: Any) -> Any:
  return func.lower(func.replace(column, " ", ""))


def clean_query_text(value: Any) -> str:
  text = str(value or "").strip()
  text = re.sub(r"\s+", " ", text)
  return text


def complex_name_variants(value: Any) -> list[str]:
  text = clean_query_text(value)
  if not text:
    return []

  compact = normalize_complex_key(text)
  candidates: list[str] = []
  add_variant(candidates, compact)

  without_parentheses = re.sub(r"\([^)]*\)", "", compact)
  add_variant(candidates, without_parentheses)

  for candidate in list(candidates):
    for suffix in GENERIC_SUFFIXES:
      if candidate.endswith(suffix) and len(candidate) > len(suffix):
        add_variant(candidates, candidate.removesuffix(suffix))

  for candidate in list(candidates):
    phase_match = re.fullmatch(r"(?P<base>.+?)(?P<number>\d+)차", candidate)
    if phase_match is not None:
      add_variant(candidates, f"{phase_match.group('base')}{phase_match.group('number')}")
      add_variant(candidates, phase_match.group("base"))
      continue

    number_match = re.fullmatch(r"(?P<base>.+?)(?P<number>\d+)", candidate)
    if number_match is not None and len(number_match.group("base")) >= 2:
      add_variant(candidates, number_match.group("base"))

  for candidate in list(candidates):
    add_variant(candidates, candidate.replace("펠리스", "팰리스"))
    add_variant(candidates, candidate.replace("레미안", "래미안"))

  return [item for item in candidates if item]


def add_variant(candidates: list[str], value: str) -> None:
  value = strip_particles(value)
  if value and value not in candidates:
    candidates.append(value)


def strip_particles(value: str) -> str:
  text = value.strip()
  changed = True
  while changed:
    changed = False
    for particle in PARTICLE_SUFFIXES:
      if text.endswith(particle) and len(text) > len(particle) + 1:
        text = text.removesuffix(particle)
        changed = True
        break
  return text


def normalize_complex_key(value: Any) -> str:
  text = clean_query_text(value)
  text = text.replace("ＡＰＴ", "apt").replace("APT", "apt")
  text = re.sub(r"[^0-9a-zA-Z가-힣()]+", "", text)
  return text.replace("펠리스", "팰리스").replace("레미안", "래미안").lower()


def is_insufficient_complex_query(query: str, variants: list[str]) -> bool:
  if not variants:
    return True
  cores = [generic_suffix_stripped(variant) for variant in variants]
  return all(core in GENERIC_CORE_NAMES for core in cores)


def generic_suffix_stripped(value: str) -> str:
  core = value
  for action in QUERY_ACTION_SUFFIXES:
    if core.endswith(action):
      core = core.removesuffix(action)
      break
  changed = True
  while changed:
    changed = False
    for suffix in GENERIC_SUFFIXES:
      if core.endswith(suffix):
        core = core.removesuffix(suffix)
        changed = True
        break
  return strip_particles(core)


def score_complex_candidate(
  row: Complex,
  variants: list[str],
  context: ComplexResolverContext,
) -> CandidateScore:
  row_keys = [
    key
    for key in (
      normalize_complex_key(row.name),
      normalize_complex_key(row.trade_name),
    )
    if key
  ]
  best_score = 0
  best_reason = ""
  best_variant = ""
  for variant in variants:
    for row_key in row_keys:
      score, reason = name_match_score(variant, row_key)
      if score > best_score:
        best_score = score
        best_reason = reason
        best_variant = variant

  if best_variant and len(best_variant) <= 2 and any(len(variant) > len(best_variant) for variant in variants):
    best_score -= 80

  score = best_score + context_score(row, variants, context)
  return CandidateScore(
    row=row,
    score=score,
    match_reason=best_reason or "partial_name",
    matched_variant=best_variant,
  )


def name_match_score(variant: str, row_key: str) -> tuple[int, str]:
  if not variant or len(variant) < 2:
    return 0, ""
  if variant == row_key:
    return 1000 + min(80, len(variant) * 4), "exact_name"
  if row_key.startswith(variant):
    return 850 + min(80, len(variant) * 4), "prefix_name"
  if variant in row_key:
    return 720 + min(80, len(variant) * 4), "partial_name"
  if row_key in variant:
    return 620 + min(80, len(row_key) * 4), "input_contains_name"
  if min(len(variant), len(row_key)) >= 4:
    similarity = SequenceMatcher(None, variant, row_key).ratio()
    if similarity >= 0.78:
      return 420 + int(similarity * 160), "similar_name"
  return 0, ""


def context_score(
  row: Complex,
  variants: list[str],
  context: ComplexResolverContext,
) -> int:
  score = phase_context_score(row, variants)

  if context.region_id is not None and row.region_id == context.region_id:
    score += 180

  address_key = normalize_complex_key(row.address)
  for keyword in context_keywords(context):
    keyword_key = normalize_complex_key(keyword)
    if keyword_key and keyword_key in address_key:
      score += 160

  anchor = context.anchor_complex
  if anchor is None:
    return score

  if row.region_id == anchor.region_id:
    score += 90

  anchor_neighborhood = neighborhood_from_address(anchor.address)
  row_neighborhood = neighborhood_from_address(row.address)
  if anchor_neighborhood and row_neighborhood and anchor_neighborhood == row_neighborhood:
    score += 220

  distance = distance_between_complexes(row, anchor)
  if distance is None:
    return score
  if distance <= 1000:
    score += 220
  elif distance <= 2500:
    score += 160
  elif distance <= DISTANCE_CONTEXT_LIMIT_M:
    score += 100
  return score


def context_keywords(context: ComplexResolverContext) -> tuple[str, ...]:
  values = list(context.address_keywords)
  if context.region_name:
    values.append(context.region_name)
  return tuple(values)


def phase_context_score(row: Complex, variants: list[str]) -> int:
  requested_phases = {
    match.group("number")
    for variant in variants
    if (match := re.search(r"(?P<number>\d+)차", variant))
  }
  if not requested_phases:
    return 0
  row_key = normalize_complex_key(row.name) + normalize_complex_key(row.trade_name)
  score = 0
  for number in requested_phases:
    if f"{number}차" in row_key:
      score = max(score, 180)
    elif re.search(rf"(?<!\d){re.escape(number)}(?!\d)", row_key):
      score = max(score, 120)
  return score


def neighborhood_from_address(address: Any) -> str:
  text = str(address or "")
  match = re.search(r"([가-힣A-Za-z0-9]+동)", text)
  return match.group(1) if match else ""


def distance_between_complexes(a: Complex, b: Complex) -> float | None:
  if a.latitude is None or a.longitude is None or b.latitude is None or b.longitude is None:
    return None
  return haversine_m(float(a.latitude), float(a.longitude), float(b.latitude), float(b.longitude))


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
  radius_m = 6371000.0
  phi1 = math.radians(lat1)
  phi2 = math.radians(lat2)
  delta_phi = math.radians(lat2 - lat1)
  delta_lambda = math.radians(lon2 - lon1)
  value = (
    math.sin(delta_phi / 2) ** 2
    + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
  )
  return radius_m * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def should_auto_resolve(
  scored: list[CandidateScore],
  query: str,
  context: ComplexResolverContext,
) -> bool:
  if len(scored) == 1:
    return True
  if not context.auto_resolve_with_context:
    return False
  if not has_strong_context(query, context):
    return False

  top = scored[0]
  second = scored[1]
  return top.score >= 900 and top.score - second.score >= 80


def has_strong_context(query: str, context: ComplexResolverContext) -> bool:
  if context.anchor_complex is not None:
    return True
  if context.region_id is not None or context.region_name or context.address_keywords:
    return True
  return re.search(r"\d+\s*차", query) is not None


def resolution_note(
  candidate: CandidateScore,
  query: str,
  context: ComplexResolverContext,
) -> str:
  name = candidate.row.name
  if context.anchor_complex is not None:
    anchor_name = context.anchor_complex.name
    return f"{query}은 {anchor_name}와 가까운 후보인 {name} 기준으로 확인했습니다."
  if context.region_name:
    return f"{query}은 {context.region_name} 문맥에 맞는 {name} 기준으로 확인했습니다."
  if context.address_keywords:
    return f"{query}은 {', '.join(context.address_keywords)} 문맥에 맞는 {name} 기준으로 확인했습니다."
  if re.search(r"\d+\s*차", query):
    return f"{query}은 차수 문맥에 맞는 {name} 기준으로 확인했습니다."
  return ""


def candidate_to_dict(item: CandidateScore) -> dict[str, Any]:
  row = item.row
  return {
    "complex_id": row.id,
    "complex_name": row.name,
    "trade_name": row.trade_name,
    "address": row.address,
    "score": item.score,
    "match_reason": item.match_reason,
    "matched_variant": item.matched_variant,
  }
