from __future__ import annotations

import json
import re
from typing import Any


MAX_CHUNK_LENGTH = 24
FALLBACK_STREAM_ANSWER = "질문을 처리했습니다."
FORBIDDEN_STREAM_TERMS = (
  "전문 에이전트",
  "handler",
  "agent",
  "tool",
  "execution",
  "planType",
  "dedupe",
  "fragment",
  "raw JSON",
  "latitude",
  "longitude",
  "위도",
  "경도",
  "좌표",
)
COORDINATE_PATTERNS = (
  re.compile(
    r"좌표는?\s*위도\s*[-+]?\d+(?:\.\d+)?\s*,?\s*경도\s*[-+]?\d+(?:\.\d+)?(?:입니다\.?|[.!?。])?",
    re.IGNORECASE,
  ),
  re.compile(
    r"위도\s*[-+]?\d+(?:\.\d+)?\s*,?\s*경도\s*[-+]?\d+(?:\.\d+)?(?:입니다\.?|[.!?。])?",
    re.IGNORECASE,
  ),
  re.compile(
    r"latitude\s*[:=]?\s*[-+]?\d+(?:\.\d+)?\s*,?\s*longitude\s*[:=]?\s*[-+]?\d+(?:\.\d+)?",
    re.IGNORECASE,
  ),
  re.compile(
    r"longitude\s*[:=]?\s*[-+]?\d+(?:\.\d+)?\s*,?\s*latitude\s*[:=]?\s*[-+]?\d+(?:\.\d+)?",
    re.IGNORECASE,
  ),
  re.compile(
    r"(?<!\d)(?:3[3-9]|4[0-3])\.\d{3,}\s*,\s*(?:12[4-9]|13[0-2])\.\d{3,}(?!\d)"
  ),
)
JSON_BLOCK_PATTERN = re.compile(r"\{[^{}]*\}")


def format_sse(event: str, data: Any) -> bytes:
  payload = json.dumps(data, ensure_ascii=False, default=str)
  return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


def chunk_answer(answer: str) -> list[str]:
  text = stream_safe_answer(answer)
  if not text:
    text = FALLBACK_STREAM_ANSWER

  chunks: list[str] = []
  current = ""
  for token in re.findall(r"\S+\s*|\n", text):
    if current and len(current) + len(token) > MAX_CHUNK_LENGTH:
      chunks.append(current)
      current = token
    else:
      current += token
  if current:
    chunks.append(current)
  return chunks or [text]


def stream_safe_answer(answer: str) -> str:
  text = normalize_answer_whitespace(answer)
  text = remove_coordinate_text(text)
  text = remove_json_fragments(text)
  if has_forbidden_stream_terms(text):
    text = remove_forbidden_sentences(text)
  return normalize_answer_whitespace(text)


def normalize_answer_whitespace(answer: str) -> str:
  text = str(answer or "").replace("\r\n", "\n").replace("\r", "\n").strip()
  text = re.sub(r"\n{3,}", "\n\n", text)
  text = re.sub(r"[ \t]+", " ", text)
  return text


def remove_coordinate_text(answer: str) -> str:
  text = answer
  for pattern in COORDINATE_PATTERNS:
    text = pattern.sub("", text)
  return normalize_answer_whitespace(text)


def remove_json_fragments(answer: str) -> str:
  text = answer
  previous = None
  while previous != text:
    previous = text
    text = JSON_BLOCK_PATTERN.sub("", text)
  return normalize_answer_whitespace(text)


def has_forbidden_stream_terms(answer: str) -> bool:
  lowered = answer.lower()
  return any(term.lower() in lowered for term in FORBIDDEN_STREAM_TERMS)


def remove_forbidden_sentences(answer: str) -> str:
  sentences = split_sentences(answer)
  kept = [
    sentence
    for sentence in sentences
    if not has_forbidden_stream_terms(sentence)
  ]
  return normalize_answer_whitespace(" ".join(kept))


def split_sentences(answer: str) -> list[str]:
  sentences = re.findall(r"[^.!?\n。]+[.!?。]?", answer)
  return [sentence.strip() for sentence in sentences if sentence.strip()]
