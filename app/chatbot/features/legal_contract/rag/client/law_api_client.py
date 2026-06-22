from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ApiResponse:
  request_url: str
  payload: dict[str, Any] | list[Any]


class LawApiClient:
  def __init__(self, timeout: float = 30.0):
    self.oc = os.getenv("LAW_API_OC", "")
    self.base_url = os.getenv("LAW_API_BASE_URL", "https://www.law.go.kr/DRF").rstrip("/")
    self.timeout = timeout

  def search_laws(self, query: str) -> ApiResponse:
    return self._get("lawSearch.do", {"target": "law", "type": "JSON", "query": query, "display": 100})

  def get_law_body(self, mst: str) -> ApiResponse:
    return self._get("lawService.do", {"target": "eflaw", "type": "JSON", "MST": mst})

  def get_term_mappings(self, query: str) -> ApiResponse:
    return self._get("lawService.do", {"target": "dlytrmRlt", "type": "JSON", "query": query})

  def _get(self, path: str, params: dict[str, Any]) -> ApiResponse:
    if not self.oc:
      raise ValueError("LAW_API_OC environment variable is required")
    actual = f"{self.base_url}/{path}?{urlencode({'OC': self.oc, **params})}"
    safe = f"{self.base_url}/{path}?{urlencode({'OC': '***', **params})}"
    request = Request(actual, headers={"Accept": "application/json", "User-Agent": "legal-rag-ingest/1.0"})
    with urlopen(request, timeout=self.timeout) as response:
      payload = json.loads(response.read().decode("utf-8-sig"))
    if not isinstance(payload, (dict, list)):
      raise ValueError("Law API returned a non-object JSON response")
    return ApiResponse(safe, payload)

  @staticmethod
  def select_current_candidate(payload: Any, expected_name: str) -> dict[str, Any]:
    candidates = _records(payload, {"법령명한글", "법령명_한글", "lawname"})
    matches = [row for row in candidates if _value(row, "법령명한글", "법령명_한글", "lawName") == expected_name]
    matches = [row for row in matches if not any(word in str(row) for word in ("폐지", "시행예정"))]
    if not matches:
      raise ValueError(f"No current exact-match law found: {expected_name}")
    return max(matches, key=lambda row: str(_value(row, "시행일자", "공포일자") or ""))


def _records(value: Any, keys: set[str]) -> list[dict[str, Any]]:
  if isinstance(value, list):
    return [item for child in value for item in _records(child, keys)]
  if not isinstance(value, dict):
    return []
  normalized = {_key(key) for key in value}
  if normalized & {_key(key) for key in keys}:
    return [value]
  return [item for child in value.values() for item in _records(child, keys)]


def _value(row: dict[str, Any], *keys: str) -> Any:
  values = {_key(key): value for key, value in row.items()}
  return next((values[_key(key)] for key in keys if _key(key) in values), None)


def _key(value: str) -> str:
  return value.replace("_", "").replace(" ", "").lower()
