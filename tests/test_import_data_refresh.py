from __future__ import annotations

import csv
from pathlib import Path


IMPORT_DIR = Path(__file__).resolve().parents[1] / "db" / "import"


def read_rows(filename: str) -> list[dict[str, str]]:
  with (IMPORT_DIR / filename).open(encoding="utf-8-sig", newline="") as input_file:
    return list(csv.DictReader(input_file))


def test_june_import_csv_refresh_counts_and_markers():
  trades = read_rows("trades.csv")
  complexes = read_rows("complexes.csv")

  assert len(trades) == 173474
  assert sum(1 for row in trades if row["deal_date"].startswith("2026-06")) == 200
  assert any(row["name"] == "BRUNNEN청담" for row in complexes)
  assert all(row["id"] != "7770024" for row in trades)
