from __future__ import annotations

import csv
import sys
from pathlib import Path


TARGET_DISTRICTS = {"강남구", "서초구", "송파구"}
EDUCATION_TYPES = {"유치원", "초등학교", "중학교", "고등학교", "특수학교"}


def main() -> int:
  if len(sys.argv) != 4:
    print("Usage: scripts/build-pois-csv.py <stations.csv> <schools.csv> <output.csv>", file=sys.stderr)
    return 2

  station_path = Path(sys.argv[1])
  school_path = Path(sys.argv[2])
  output_path = Path(sys.argv[3])

  rows = station_rows(station_path) + education_rows(school_path)
  output_path.parent.mkdir(parents=True, exist_ok=True)

  with output_path.open("w", encoding="utf-8-sig", newline="") as output_file:
    writer = csv.DictWriter(output_file, fieldnames=["category", "name", "subtype", "latitude", "longitude"])
    writer.writeheader()
    writer.writerows(rows)

  print(f"wrote {len(rows)} rows to {output_path}")
  print(f"station rows: {sum(row['category'] == 'station' for row in rows)}")
  print(f"education rows: {sum(row['category'] == 'education' for row in rows)}")
  return 0


def station_rows(path: Path) -> list[dict[str, str]]:
  with path.open(encoding="cp949", newline="") as input_file:
    reader = csv.DictReader(input_file)
    return [
      {
        "category": "station",
        "name": station_name(row["역사명"]),
        "subtype": row["호선"].strip(),
        "latitude": normalize_coordinate(row["위도"]),
        "longitude": normalize_coordinate(row["경도"]),
      }
      for row in reader
      if has_coordinates(row)
    ]


def education_rows(path: Path) -> list[dict[str, str]]:
  with path.open(encoding="cp949", newline="") as input_file:
    reader = csv.DictReader(input_file)
    return [
      {
        "category": "education",
        "name": row["학교"].strip(),
        "subtype": row["학교급"].strip(),
        "latitude": normalize_coordinate(row["위도"]),
        "longitude": normalize_coordinate(row["경도"]),
      }
      for row in reader
      if (
        row["자치구"].strip() in TARGET_DISTRICTS
        and row["학교급"].strip() in EDUCATION_TYPES
        and has_coordinates(row)
      )
    ]


def station_name(value: str) -> str:
  name = value.strip()
  return name if name.endswith("역") else f"{name}역"


def has_coordinates(row: dict[str, str]) -> bool:
  return bool(row.get("위도", "").strip() and row.get("경도", "").strip())


def normalize_coordinate(value: str) -> str:
  return str(float(value.strip()))


if __name__ == "__main__":
  raise SystemExit(main())
