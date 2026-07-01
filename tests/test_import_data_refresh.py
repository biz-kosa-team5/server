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

  assert len(trades) == 173764
  assert sum(1 for row in trades if row["deal_date"].startswith("2026-06")) == 260
  assert any(row["name"] == "BRUNNEN청담" for row in complexes)
  lucky = next(row for row in complexes if row["id"] == "3426")
  assert lucky["name"] == "역삼럭키"
  assert lucky["trade_name"] == "럭키(963)"
  lucky_recent = {
    (row["deal_date"], row["deal_amount"], row["excl_area"], row["floor"])
    for row in trades
    if row["complex_id"] == "3426" and row["deal_date"] >= "2026-05-01"
  }
  assert ("2026-06-14", "262000", "84.97", "11") in lucky_recent
  assert ("2026-05-31", "256000", "84.97", "3") in lucky_recent
  assert ("2026-05-23", "285000", "124.66", "9") in lucky_recent
  assert all(row["id"] != "7770024" for row in trades)
