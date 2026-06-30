from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from functools import lru_cache
from typing import Any


TAVILY_SEARCH_URL = "https://api.tavily.com/search"
DEFAULT_TIMEOUT_SECONDS = 4
REDEVELOPMENT_KEYWORDS = ("재개발", "재건축", "정비사업", "호재", "미래", "전망", "투자", "투자가치", "투자 가치")

logger = logging.getLogger(__name__)


def should_search_redevelopment_context(text: str) -> bool:
  return any(keyword in text for keyword in REDEVELOPMENT_KEYWORDS)


def search_redevelopment_context(
  complex_name: str,
  address: str | None = None,
  max_results: int = 3,
) -> list[dict[str, str]]:
  """Tavily로 재개발/재건축/정비사업 공개 정보를 짧게 조회한다."""
  return list(cached_redevelopment_context(complex_name, address or "", max_results))


@lru_cache(maxsize=256)
def cached_redevelopment_context(
  complex_name: str,
  address: str,
  max_results: int,
) -> tuple[dict[str, str], ...]:
  api_key = os.getenv("TAVILY_API_KEY")
  if not api_key:
    return tuple()

  query_parts = [part for part in (address, complex_name, "재건축 재개발 정비사업 호재") if part]
  payload = {
    "api_key": api_key,
    "query": " ".join(query_parts),
    "search_depth": "basic",
    "max_results": max(1, min(max_results, 5)),
    "include_answer": False,
    "include_raw_content": False,
  }

  request = urllib.request.Request(
    TAVILY_SEARCH_URL,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
  )

  try:
    with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
      body = json.loads(response.read().decode("utf-8"))
  except (OSError, urllib.error.URLError, json.JSONDecodeError):
    logger.exception("Failed to search redevelopment context")
    return tuple()

  return tuple(compact_search_results(body.get("results", []), max_results))


def compact_search_results(results: Any, max_results: int) -> list[dict[str, str]]:
  if not isinstance(results, list):
    return []

  compacted = []
  seen_urls = set()
  for item in results:
    if not isinstance(item, dict):
      continue
    title = clean_result_text(item.get("title"))
    url = clean_result_text(item.get("url"))
    content = clean_result_text(item.get("content"))
    if not title or not url or url in seen_urls:
      continue
    compacted.append({
      "title": title,
      "url": url,
      "content": content[:180] if content else "",
    })
    seen_urls.add(url)
    if len(compacted) >= max_results:
      break
  return compacted


def clean_result_text(value: Any) -> str:
  if value is None:
    return ""
  return str(value).strip()
