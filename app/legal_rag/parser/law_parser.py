from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import parse_qs, urlparse


@dataclass(frozen=True)
class ParsedDocument:
  law_id: str; mst: str | None; law_name: str; law_type: str | None; ministry: str | None
  article_no: str; article_title: str | None; paragraph_no: str; doc_type: str; content: str
  metadata: dict[str, Any]; source_url: str | None; effective_date: date


def parse_law(payload: Any, source_url: str | None) -> list[ParsedDocument]:
  info = _first_dict(payload, {"기본정보", "basicinfo", "lawinfo"}) or payload
  law_id = _text(_find(info, "법령ID", "lawId")); name = _text(_find(info, "법령명_한글", "법령명한글", "lawName"))
  effective = _date(_find(info, "시행일자", "effectiveDate"))
  if not law_id or not name or not effective:
    raise ValueError("Required law metadata is missing")
  common = dict(law_id=law_id, mst=_optional(_find(info, "법령일련번호", "MST")) or _mst_from_url(source_url), law_name=name,
    law_type=_content(_find(info, "법령구분명", "법종구분", "lawType")),
    ministry=_content(_find(info, "소관부처명", "소관부처", "ministry")),
    source_url=source_url, effective_date=effective)
  result: list[ParsedDocument] = []
  for article in _records(payload, {"조문번호", "articleno"}):
    if _optional(_find(article, "조문여부")) not in (None, "조문"):
      continue
    number = _text(_find(article, "조문번호", "articleNo"))
    branch = _optional(_find(article, "조문가지번호", "articleBranchNo"))
    content = _structured_content(article, {"조문내용", "articletext", "항내용", "paragraphtext", "호내용", "목내용"})
    title = _optional(_find(article, "조문제목", "articleTitle"))
    article_no = number if number.startswith("제") else f"제{number}조"
    if branch and branch != "0" and "의" not in article_no:
      article_no = f"{article_no}의{branch}"
    change_type = _optional(_find(article, "조문제개정유형")) or ""
    if not number or not content or "삭제" in f"{title} {content} {change_type}" or article_no.startswith("부칙"):
      continue
    result.append(ParsedDocument(**common, article_no=article_no, article_title=title, paragraph_no="",
      doc_type="article", content=content, metadata={"law_id": law_id, "law_name": name, "article_branch_no": branch}))
    if len(content) > 2000:
      for paragraph in _records(article, {"항번호", "paragraphno"}):
        text = _structured_content(paragraph, {"항내용", "paragraphtext", "호내용", "목내용"})
        if text:
          result.append(ParsedDocument(**common, article_no=article_no, article_title=title,
            paragraph_no=_text(_find(paragraph, "항번호", "paragraphNo")) or "1", doc_type="paragraph",
            content=text, metadata={"article_branch_no": branch}))
  return result


def _records(value: Any, keys: set[str]) -> list[dict[str, Any]]:
  if isinstance(value, list): return [x for child in value for x in _records(child, keys)]
  if not isinstance(value, dict): return []
  if {_key(k) for k in value} & {_key(k) for k in keys}: return [value]
  return [x for child in value.values() for x in _records(child, keys)]


def _find(value: Any, *keys: str) -> Any:
  wanted = {_key(k) for k in keys}
  if isinstance(value, dict):
    for key, child in value.items():
      if _key(key) in wanted: return child
    for child in value.values():
      found = _find(child, *keys)
      if found is not None: return found
  if isinstance(value, list):
    for child in value:
      found = _find(child, *keys)
      if found is not None: return found
  return None


def _first_dict(value: Any, keys: set[str]) -> dict[str, Any] | None:
  found = _find(value, *keys)
  return found if isinstance(found, dict) else None


def _date(value: Any) -> date | None:
  digits = re.sub(r"\D", "", _text(value)); return date(int(digits[:4]), int(digits[4:6]), int(digits[6:])) if len(digits) == 8 else None


def _structured_content(value: Any, content_keys: set[str]) -> str:
  wanted = {_key(key) for key in content_keys}
  parts: list[str] = []

  def visit(node: Any) -> None:
    if isinstance(node, dict):
      for key, child in node.items():
        if _key(key) in wanted:
          text = _clean(child)
          if text and text not in parts:
            parts.append(text)
        if isinstance(child, (dict, list)):
          visit(child)
    elif isinstance(node, list):
      for child in node:
        visit(child)

  visit(value)
  return " ".join(parts)


def _clean(value: Any) -> str:
  if isinstance(value, list):
    return " ".join(filter(None, (_clean(item) for item in value)))
  if isinstance(value, dict):
    return _clean(value.get("content")) if "content" in value else ""
  return re.sub(r"\s+", " ", _text(value)).strip()


def _content(value: Any) -> str | None:
  if isinstance(value, dict):
    value = value.get("content")
  return _optional(value)


def _mst_from_url(source_url: str | None) -> str | None:
  if not source_url:
    return None
  values = parse_qs(urlparse(source_url).query)
  return next(iter(values.get("MST", values.get("mst", []))), None)


def _optional(value: Any) -> str | None: return _text(value).strip() or None
def _text(value: Any) -> str: return "" if value is None else str(value)
def _key(value: str) -> str: return value.replace("_", "").replace(" ", "").lower()
