"""
fallback answer에서 사용하는 formatter 공개 API입니다.
handler observation을 안전한 한국어 문장으로 바꾸는 helper만 노출합니다.
"""
from .common import (
  clean_text,
  collect_result_messages,
  dedupe,
  first_non_empty,
  format_failure_reason,
)
from .result import format_result_messages

__all__ = [
  "clean_text",
  "collect_result_messages",
  "dedupe",
  "first_non_empty",
  "format_failure_reason",
  "format_result_messages",
]
