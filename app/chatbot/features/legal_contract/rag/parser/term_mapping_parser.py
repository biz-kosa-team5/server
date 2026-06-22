from __future__ import annotations

from dataclasses import dataclass
from typing import Any


RELATION_TYPES = {
  "동의어": ("SYNONYM", 100),
  "상위어": ("BROADER", 80),
  "하위어": ("NARROWER", 70),
  "연관어": ("RELATED", 50),
}


@dataclass(frozen=True)
class ParsedTermMapping:
  daily_term: str
  legal_term: str
  relation_type: str
  priority: int
  raw_data: dict[str, Any]


def parse_term_mappings(payload: Any) -> list[ParsedTermMapping]:
  root = payload.get("dlytrmRltService", {}) if isinstance(payload, dict) else {}
  daily = root.get("일상용어") if isinstance(root, dict) else None
  if not isinstance(daily, dict):
    return []
  daily_term = str(daily.get("일상용어명") or root.get("키워드") or "").strip()
  linked = daily.get("연계용어", [])
  if isinstance(linked, dict):
    linked = [linked]
  result: list[ParsedTermMapping] = []
  for item in linked if isinstance(linked, list) else []:
    if not isinstance(item, dict):
      continue
    legal_term = str(item.get("법령용어명") or "").strip()
    relation_name = str(item.get("용어관계") or "").strip()
    if not daily_term or not legal_term or relation_name not in RELATION_TYPES:
      continue
    relation_type, priority = RELATION_TYPES[relation_name]
    result.append(ParsedTermMapping(
      daily_term=daily_term,
      legal_term=legal_term,
      relation_type=relation_type,
      priority=priority,
      raw_data={
        "source": "law_api",
        "relation_name": relation_name,
        "relation_code": item.get("용어관계코드"),
        "note": item.get("비고"),
        "source_id": item.get("id"),
      },
    ))
  return result
