from __future__ import annotations

from typing import Any


def compact_none(values: dict[str, Any]) -> dict[str, Any]:
  return {
    key: value
    for key, value in values.items()
    if value is not None
  }
