"""
앱 DB 엔진과 세션을 구성하고 CSV import 데이터로 초기 seed를 수행합니다.
운영 기본값은 db/import를 사용하며, 테스트는 DATA_IMPORT_DIR로 고정 fixture CSV를 주입할 수 있습니다.
"""
from __future__ import annotations

import csv
import os
from collections.abc import Callable, Generator
from pathlib import Path
from threading import Lock
from typing import TypeVar

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import load_environment
from .models import Base, Complex, Poi, Region, Trade


DEFAULT_DATABASE_URL = "sqlite+pysqlite:///:memory:"
DEFAULT_IMPORT_DIR = Path(__file__).resolve().parents[1] / "db" / "import"
BATCH_SIZE = 1000

load_environment()
database_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
import_dir = Path(os.getenv("DATA_IMPORT_DIR", str(DEFAULT_IMPORT_DIR))).expanduser()
engine = create_engine(
  database_url,
  connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {},
  poolclass=StaticPool if database_url == DEFAULT_DATABASE_URL else None,
  future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
_initialized = False
_initialization_lock = Lock()

T = TypeVar("T")


def get_session() -> Generator[Session, None, None]:
  ensure_initialized()
  with SessionLocal() as session:
    yield session


def initialize_database(target_engine: Engine = engine) -> None:
  Base.metadata.create_all(bind=target_engine)
  with SessionLocal() as session:
    if session.query(Region).first() is not None:
      return
    seed(session)
    session.commit()


def ensure_initialized() -> None:
  global _initialized
  if _initialized:
    return
  with _initialization_lock:
    if _initialized:
      return
    initialize_database()
    _initialized = True


def seed(session: Session) -> None:
  import_regions(session)
  import_complexes(session)
  import_trades(session)
  import_pois(session)


def import_regions(session: Session) -> None:
  add_csv_objects(
    session,
    "regions.csv",
    lambda row: Region(
      id=to_int(row["id"]),
      code=row["code"],
      name=row["name"],
      type=row["type"],
      parent_id=to_optional_int(row["parent_id"]),
      center_lat=to_float(row["center_lat"]),
      center_lng=to_float(row["center_lng"]),
      unit_cnt_sum=to_optional_int(row["unit_cnt_sum"]),
    ),
  )


def import_complexes(session: Session) -> None:
  add_csv_objects(
    session,
    "complexes.csv",
    lambda row: Complex(
      id=to_int(row["id"]),
      region_id=to_int(row["region_id"]),
      parcel_id=to_int(row["parcel_id"]),
      pnu=to_optional_text(row["pnu"]),
      name=row["name"],
      trade_name=to_optional_text(row["trade_name"]),
      address=to_optional_text(row["address"]),
      latitude=to_optional_float(row["latitude"]),
      longitude=to_optional_float(row["longitude"]),
      dong_cnt=to_optional_int(row["dong_cnt"]),
      unit_cnt=to_optional_int(row["unit_cnt"]),
      use_date=to_optional_text(row["use_date"]),
    ),
  )


def import_trades(session: Session) -> None:
  add_csv_objects(
    session,
    "trades.csv",
    lambda row: Trade(
      id=to_int(row["id"]),
      complex_id=to_int(row["complex_id"]),
      deal_date=row["deal_date"],
      deal_amount=to_int(row["deal_amount"]),
      excl_area=to_float(row["excl_area"]),
      floor=to_optional_int(row["floor"]),
      apt_dong=to_optional_text(row["apt_dong"]),
    ),
  )


def import_pois(session: Session) -> None:
  add_csv_objects(
    session,
    "pois.csv",
    lambda row: Poi(
      category=row["category"],
      name=row["name"],
      subtype=row["subtype"],
      latitude=to_float(row["latitude"]),
      longitude=to_float(row["longitude"]),
    ),
  )


def add_csv_objects(session: Session, filename: str, factory: Callable[[dict[str, str]], T]) -> None:
  batch: list[T] = []
  for row in read_import_csv(filename):
    batch.append(factory(row))
    if len(batch) >= BATCH_SIZE:
      session.add_all(batch)
      session.flush()
      batch.clear()
  if batch:
    session.add_all(batch)
    session.flush()


def read_import_csv(filename: str) -> Generator[dict[str, str], None, None]:
  path = import_dir / filename
  with path.open(encoding="utf-8-sig", newline="") as input_file:
    yield from csv.DictReader(input_file)


def to_optional_text(value: str | None) -> str | None:
  if value is None or value == "":
    return None
  return value


def to_int(value: str) -> int:
  return int(value)


def to_optional_int(value: str | None) -> int | None:
  if value is None or value == "":
    return None
  return int(value)


def to_float(value: str) -> float:
  return float(value)


def to_optional_float(value: str | None) -> float | None:
  if value is None or value == "":
    return None
  return float(value)
