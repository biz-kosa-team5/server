from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any, Iterable

from .ui_payload import iter_domain_results


MEMORY_VERSION = "v1"
MAX_MEMORY_ITEMS = 5
MEMORY_TTL_DAYS = 7

ACTIVE_COMPLEX_REFERENCES = (
  "그거",
  "그 단지",
  "이 단지",
  "방금",
  "위에",
)
REGION_REFERENCES = (
  "그 지역",
  "거기 지역",
)
ORDINAL_PATTERNS: tuple[tuple[re.Pattern[str], int], ...] = (
  (re.compile(r"(첫\s*번째\s*(?:거|것|단지)?|1\s*번\s*(?:거|것|단지)?)"), 1),
  (re.compile(r"(두\s*번째\s*(?:거|것|단지)?|2\s*번\s*(?:거|것|단지)?)"), 2),
  (re.compile(r"(세\s*번째\s*(?:거|것|단지)?|3\s*번\s*(?:거|것|단지)?)"), 3),
)
PARTIAL_PATTERN = re.compile(r"그중\s+(?P<name>[가-힣A-Za-z0-9()]+?)(?P<particle>만|은|는|이|가|을|를)?(?=\s|$)")
CONTEXT_ITEM_MENTION_PATTERN = re.compile(
  r"^(?P<mention>.+?)(?P<particle>으로|로|은|는|이|가|을|를)?(?P<rest>\s*(?:봐줘|해줘|알려줘|보여줘|비교해줘|비교|최근.*|시세.*|위치.*|실거래.*))$"
)
MENTION_STOPWORDS = {
  "그중",
  "그거",
  "거기",
  "단지",
  "아파트",
  "봐줘",
  "해줘",
  "알려줘",
  "보여줘",
  "비교",
  "비교해줘",
}


def normalize_conversation_context(value: Any) -> dict[str, Any] | None:
  if not isinstance(value, dict):
    return None
  if clean_text(value.get("version")) != MEMORY_VERSION:
    return None

  context: dict[str, Any] = {"version": MEMORY_VERSION}
  active_region = normalize_region(value.get("activeRegion"))
  active_complex = normalize_complex(value.get("activeComplex"))
  items = normalize_items(value.get("items"))

  if active_region:
    context["activeRegion"] = active_region
  if active_complex:
    context["activeComplex"] = active_complex
  if items:
    context["items"] = items

  for key in ("lastHandler", "lastQueryType", "updatedAt", "expiresAt"):
    text = clean_text(value.get(key))
    if text:
      context[key] = text

  return context if len(context) > 1 else None


def normalize_region(value: Any) -> dict[str, Any] | None:
  if not isinstance(value, dict):
    return None
  name = clean_text(value.get("name"))
  if not name:
    return None
  region: dict[str, Any] = {"name": name}
  code = clean_text(value.get("code"))
  region_type = clean_text(value.get("type"))
  if code:
    region["code"] = code
  if region_type:
    region["type"] = region_type
  return region


def normalize_complex(value: Any) -> dict[str, Any] | None:
  if not isinstance(value, dict):
    return None
  name = clean_text(value.get("complexName") or value.get("complex_name") or value.get("name"))
  if not name:
    return None
  complex_item: dict[str, Any] = {"complexName": name}
  complex_id = to_int_or_none(value.get("complexId") or value.get("complex_id"))
  address = clean_text(value.get("address"))
  if complex_id is not None:
    complex_item["complexId"] = complex_id
  if address:
    complex_item["address"] = address
  return complex_item


def normalize_items(value: Any) -> list[dict[str, Any]]:
  if not isinstance(value, list):
    return []
  items = []
  for position, item in enumerate(value[:MAX_MEMORY_ITEMS], start=1):
    if not isinstance(item, dict):
      continue
    normalized = normalize_memory_item(item, fallback_index=position)
    if normalized:
      items.append(normalized)
  return items


def normalize_memory_item(value: dict[str, Any], *, fallback_index: int) -> dict[str, Any] | None:
  target = normalize_complex(value)
  if target is None:
    return None
  item = {
    "index": to_int_or_none(value.get("index")) or fallback_index,
    "kind": clean_text(value.get("kind")) or "complex",
    **target,
  }
  trade_id = to_int_or_none(value.get("tradeId") or value.get("trade_id"))
  deal_amount = to_int_or_none(value.get("dealAmount") or value.get("deal_amount"))
  deal_date = clean_text(value.get("dealDate") or value.get("deal_date"))
  if trade_id is not None:
    item["tradeId"] = trade_id
  if deal_date:
    item["dealDate"] = deal_date
  if deal_amount is not None:
    item["dealAmount"] = deal_amount
  return item


def resolve_contextual_question(question: str, context: dict[str, Any] | None) -> tuple[str, dict[str, Any]]:
  text = str(question or "").strip()
  if not text:
    return text, inactive_resolution("empty_question")
  if not context:
    return text, inactive_resolution("missing_context")

  ordinal = resolve_ordinal_reference(text, context)
  if ordinal is not None:
    return ordinal

  partial = resolve_partial_name_reference(text, context)
  if partial is not None:
    return partial

  mention = resolve_context_item_mention(text, context)
  if mention is not None:
    return mention

  active_region = resolve_active_region_reference(text, context)
  if active_region is not None:
    return active_region

  active_complex = resolve_active_complex_reference(text, context)
  if active_complex is not None:
    return active_complex

  if has_reference_expression(text):
    return text, inactive_resolution("target_not_found")
  return text, inactive_resolution("no_reference")


def resolve_ordinal_reference(question: str, context: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
  items = context.get("items") if isinstance(context.get("items"), list) else []
  if not items:
    return None
  for pattern, ordinal in ORDINAL_PATTERNS:
    match = pattern.search(question)
    if match is None:
      continue
    item = item_by_index(items, ordinal)
    if item is None:
      return question, inactive_resolution("ordinal_item_not_found")
    target = clean_text(item.get("complexName"))
    if not target:
      return question, inactive_resolution("ordinal_item_not_found")
    return (
      replace_match(question, match, target),
      applied_resolution("ordinal_item", match.group(1), target),
    )
  return None


def resolve_partial_name_reference(question: str, context: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
  match = PARTIAL_PATTERN.search(question)
  if match is None:
    return None
  partial = normalize_match_text(match.group("name"))
  if not partial:
    return question, inactive_resolution("partial_name_missing")
  items = context.get("items") if isinstance(context.get("items"), list) else []
  matches = [
    item
    for item in items
    if partial in normalize_match_text(item.get("complexName"))
    or partial in normalize_match_text(item.get("address"))
  ]
  if len(matches) != 1:
    reason = "partial_name_ambiguous" if len(matches) > 1 else "partial_name_not_found"
    return question, inactive_resolution(reason)
  target = clean_text(matches[0].get("complexName"))
  if not target:
    return question, inactive_resolution("partial_name_not_found")
  particle = match.group("particle") or ""
  return (
    f"{question[:match.start()]}{target}{particle}{question[match.end():]}",
    applied_resolution("partial_item_name", match.group(0), target),
  )


def resolve_context_item_mention(question: str, context: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
  items = context.get("items") if isinstance(context.get("items"), list) else []
  if not items:
    return None
  if any(token in question for token in ACTIVE_COMPLEX_REFERENCES + REGION_REFERENCES + ("거기", "그중")):
    return None

  match = CONTEXT_ITEM_MENTION_PATTERN.search(question)
  if match is None:
    return None

  mention = clean_text(match.group("mention"))
  tokens = mention_tokens(mention)
  if not tokens:
    return None

  matches = [
    item
    for item in items
    if item_matches_tokens(item, tokens)
  ]
  if len(matches) != 1:
    return None

  target = clean_text(matches[0].get("complexName"))
  if not target:
    return question, inactive_resolution("context_item_mention_not_found")

  particle = match.group("particle") or ""
  rest = match.group("rest") or ""
  return (
    f"{target}{particle}{rest}",
    applied_resolution("context_item_mention", mention, target),
  )


def resolve_active_region_reference(question: str, context: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
  region = normalize_region(context.get("activeRegion"))
  if region is None:
    return None
  target = region["name"]

  for token in REGION_REFERENCES:
    position = question.find(token)
    if position >= 0:
      return replace_span(question, position, position + len(token), target), applied_resolution(
        "active_region",
        token,
        target,
      )

  match = re.search(r"거기", question)
  if match is None:
    return None
  if not prefers_region_reference(question):
    return None
  return (
    replace_match(question, match, target),
    applied_resolution("active_region", match.group(0), target),
  )


def resolve_active_complex_reference(question: str, context: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
  complex_item = normalize_complex(context.get("activeComplex"))
  if complex_item is None:
    return None
  target = complex_item["complexName"]
  for token in ACTIVE_COMPLEX_REFERENCES:
    position = question.find(token)
    if position < 0:
      continue
    return (
      replace_span(question, position, position + len(token), target),
      applied_resolution("active_complex", token, target),
    )
  match = re.search(r"거기", question)
  if match is None:
    return None
  return (
    replace_match(question, match, target),
    applied_resolution("active_complex", match.group(0), target),
  )


def prefers_region_reference(question: str) -> bool:
  return any(token in question for token in (
    "지역",
    "동",
    "구",
    "최신 실거래",
    "최근 실거래",
    "실거래",
    "거래",
    "추천",
    "목록",
    "더 보여",
  ))


def has_reference_expression(question: str) -> bool:
  if any(token in question for token in ACTIVE_COMPLEX_REFERENCES + REGION_REFERENCES + ("거기", "그중")):
    return True
  return any(pattern.search(question) for pattern, _ in ORDINAL_PATTERNS)


def item_by_index(items: list[Any], ordinal: int) -> dict[str, Any] | None:
  for item in items:
    if isinstance(item, dict) and to_int_or_none(item.get("index")) == ordinal:
      return item
  index = ordinal - 1
  if 0 <= index < len(items) and isinstance(items[index], dict):
    return items[index]
  return None


def mention_tokens(value: str) -> list[str]:
  tokens = []
  for raw_token in re.findall(r"[가-힣A-Za-z0-9()]+", value):
    token = normalize_match_text(strip_particle(raw_token))
    if len(token) < 2 or token in MENTION_STOPWORDS:
      continue
    tokens.append(token)
  return tokens


def item_matches_tokens(item: dict[str, Any], tokens: list[str]) -> bool:
  combined = normalize_match_text(
    " ".join([
      clean_text(item.get("complexName")),
      clean_text(item.get("address")),
    ])
  )
  return bool(combined) and all(token in combined for token in tokens)


def strip_particle(value: str) -> str:
  text = clean_text(value)
  for particle in ("으로", "로", "은", "는", "이", "가", "을", "를", "만"):
    if text.endswith(particle) and len(text) > len(particle) + 1:
      return text.removesuffix(particle)
  return text


def build_conversation_memory_patch(response_dict: dict[str, Any]) -> dict[str, Any] | None:
  domain_results = [
    result
    for result in iter_domain_results(response_dict)
    if is_memory_result(result)
  ]
  if not domain_results:
    return None

  patch: dict[str, Any] = {
    "version": MEMORY_VERSION,
    "items": [],
  }
  items: list[dict[str, Any]] = []
  for result in domain_results:
    patch["lastHandler"] = clean_text(result.get("handler"))
    patch["lastQueryType"] = result_query_type(result)
    active_region = active_region_from_result(result)
    if active_region:
      patch["activeRegion"] = active_region
    active_complex = active_complex_from_result(result)
    if active_complex:
      patch["activeComplex"] = active_complex
    items.extend(memory_items_from_result(result))

  patch["items"] = dedupe_memory_items(items)[:MAX_MEMORY_ITEMS]
  now = datetime.now(timezone.utc)
  patch["updatedAt"] = isoformat_z(now)
  patch["expiresAt"] = isoformat_z(now + timedelta(days=MEMORY_TTL_DAYS))

  return {
    key: value
    for key, value in patch.items()
    if value not in (None, "", [])
  }


def is_memory_result(result: dict[str, Any]) -> bool:
  if result_candidate_rows(result):
    return True
  if result.get("success") is not True:
    return False
  handler = clean_text(result.get("handler"))
  if handler == "simple_lookup":
    return clean_text(result.get("query_type")) in {
      "trade_history",
      "region_trade_history",
      "region_price_ranking",
    }
  if handler in {"recommendation", "comparison", "price_trend"}:
    return True
  return False


def result_query_type(result: dict[str, Any]) -> str:
  handler = clean_text(result.get("handler"))
  if handler == "simple_lookup":
    return clean_text(result.get("query_type"))
  if handler == "price_trend":
    return clean_text(result.get("observation_type"))
  return handler


def active_region_from_result(result: dict[str, Any]) -> dict[str, Any] | None:
  handler = clean_text(result.get("handler"))
  if handler == "simple_lookup":
    query_type = clean_text(result.get("query_type"))
    if query_type in {"region_trade_history", "region_price_ranking"}:
      criteria = dict_value(result.get("criteria"))
      name = clean_text(criteria.get("target_name"))
      if name:
        region: dict[str, Any] = {"name": name}
        target_type = clean_text(criteria.get("target_type"))
        if target_type:
          region["type"] = target_type
        return region
  if handler == "price_trend":
    criteria = dict_value(result.get("criteria"))
    if clean_text(criteria.get("target_type")) == "region":
      name = clean_text(criteria.get("target_name"))
      if name:
        return {"name": name, "type": "region"}
  return None


def active_complex_from_result(result: dict[str, Any]) -> dict[str, Any] | None:
  handler = clean_text(result.get("handler"))
  if handler == "simple_lookup" and clean_text(result.get("query_type")) == "trade_history":
    return first_complex_from_rows(list_rows(result.get("data")))
  if handler == "price_trend":
    criteria = dict_value(result.get("criteria"))
    if clean_text(criteria.get("target_type")) == "complex":
      name = clean_text(criteria.get("target_name"))
      if name:
        return compact_dict({
          "complexId": to_int_or_none(criteria.get("complex_id")),
          "complexName": name,
        })
  return None


def memory_items_from_result(result: dict[str, Any]) -> list[dict[str, Any]]:
  candidates = result_candidate_rows(result)
  if candidates:
    return [
      memory_item_from_row(row, index)
      for index, row in enumerate(candidates[:MAX_MEMORY_ITEMS], start=1)
    ]

  handler = clean_text(result.get("handler"))
  if handler == "simple_lookup":
    query_type = clean_text(result.get("query_type"))
    if query_type in {"trade_history", "region_trade_history", "region_price_ranking"}:
      return [
        memory_item_from_row(row, index)
        for index, row in enumerate(list_rows(result.get("data")), start=1)
      ]
  if handler in {"recommendation", "comparison"}:
    return [
      memory_item_from_row(row, index)
      for index, row in enumerate(list_rows(result.get("results")), start=1)
    ]
  if handler == "price_trend":
    active_complex = active_complex_from_result(result)
    if active_complex:
      return [compact_dict({"index": 1, "kind": "complex", **active_complex})]
  return []


def result_candidate_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
  rows = list_rows(result.get("candidates"))
  if rows:
    return rows

  candidate_groups = list_rows(result.get("candidateGroups"))
  candidates: list[dict[str, Any]] = []
  for group in candidate_groups:
    candidates.extend(list_rows(group.get("candidates")))
  return candidates


def first_complex_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
  for row in rows:
    item = compact_dict({
      "complexId": to_int_or_none(row.get("complexId") or row.get("complex_id")),
      "complexName": clean_text(row.get("complexName") or row.get("complex_name")),
      "address": clean_text(row.get("address")),
    })
    if item.get("complexName"):
      return item
  return None


def memory_item_from_row(row: dict[str, Any], index: int) -> dict[str, Any]:
  return compact_dict({
    "index": index,
    "kind": "complex",
    "complexId": to_int_or_none(row.get("complexId") or row.get("complex_id")),
    "complexName": clean_text(row.get("complexName") or row.get("complex_name")),
    "address": clean_text(row.get("address")),
    "tradeId": to_int_or_none(row.get("tradeId") or row.get("trade_id")),
    "dealDate": clean_text(row.get("dealDate") or row.get("deal_date") or row.get("latestDealDate")),
    "dealAmount": to_int_or_none(row.get("dealAmount") or row.get("deal_amount") or row.get("latestDealAmount")),
  })


def dedupe_memory_items(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
  deduped: list[dict[str, Any]] = []
  seen: set[str] = set()
  for item in items:
    if not item.get("complexName"):
      continue
    key = memory_item_key(item)
    if key in seen:
      continue
    seen.add(key)
    deduped.append({
      **item,
      "index": len(deduped) + 1,
    })
  return deduped


def memory_item_key(item: dict[str, Any]) -> str:
  complex_id = to_int_or_none(item.get("complexId"))
  if complex_id is not None:
    return f"id:{complex_id}"
  return "name:{name}|address:{address}".format(
    name=normalize_match_text(item.get("complexName")),
    address=normalize_match_text(item.get("address")),
  )


def applied_resolution(source: str, matched_text: str, target: str) -> dict[str, Any]:
  return {
    "applied": True,
    "source": source,
    "matchedText": matched_text,
    "resolvedTarget": target,
  }


def inactive_resolution(reason: str) -> dict[str, Any]:
  return {
    "applied": False,
    "reason": reason,
  }


def replace_match(question: str, match: re.Match[str], replacement: str) -> str:
  return replace_span(question, match.start(), match.end(), replacement)


def replace_span(question: str, start: int, end: int, replacement: str) -> str:
  return f"{question[:start]}{replacement}{question[end:]}"


def list_rows(value: Any) -> list[dict[str, Any]]:
  if not isinstance(value, list):
    return []
  return [item for item in value if isinstance(item, dict)]


def dict_value(value: Any) -> dict[str, Any]:
  return value if isinstance(value, dict) else {}


def compact_dict(value: dict[str, Any]) -> dict[str, Any]:
  return {
    key: item
    for key, item in value.items()
    if item not in (None, "", [])
  }


def clean_text(value: Any) -> str:
  if value is None:
    return ""
  return str(value).strip()


def normalize_match_text(value: Any) -> str:
  return re.sub(r"\s+", "", clean_text(value)).lower()


def to_int_or_none(value: Any) -> int | None:
  if value in (None, ""):
    return None
  try:
    return int(value)
  except (TypeError, ValueError):
    return None


def isoformat_z(value: datetime) -> str:
  return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
