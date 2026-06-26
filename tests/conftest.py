"""
pytest 실행을 로컬 DATABASE_URL과 운영 CSV에서 분리합니다.
모든 테스트가 인메모리 SQLite와 tests/fixtures/import 데이터를 사용하도록 환경 변수를 먼저 고정합니다.
"""
from __future__ import annotations

import os
from pathlib import Path


FIXTURE_IMPORT_DIR = Path(__file__).resolve().parent / "fixtures" / "import"

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["DATA_IMPORT_DIR"] = str(FIXTURE_IMPORT_DIR)
