from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import Lock

_CONNECTION: sqlite3.Connection | None = None
_LOCK = Lock()


def get_connection() -> sqlite3.Connection:
  global _CONNECTION
  with _LOCK:
    if _CONNECTION is None:
      _CONNECTION = sqlite3.connect(":memory:", check_same_thread=False)
      _CONNECTION.row_factory = sqlite3.Row
      initialize(_CONNECTION)
    return _CONNECTION


def initialize(connection: sqlite3.Connection) -> None:
  schema_path = Path(__file__).with_name("schema.sql")
  seed_path = Path(__file__).with_name("seed.sql")
  connection.executescript(schema_path.read_text(encoding="utf-8"))
  connection.executescript(seed_path.read_text(encoding="utf-8"))
  connection.commit()
