from __future__ import annotations

import os
from collections.abc import Generator
from threading import Lock

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base, Complex, Region, Trade

DEFAULT_DATABASE_URL = "sqlite+pysqlite:///:memory:"

database_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
engine = create_engine(
  database_url,
  connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {},
  poolclass=StaticPool if database_url == DEFAULT_DATABASE_URL else None,
  future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
_initialized = False
_initialization_lock = Lock()


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
  session.add_all([
    Region(id=11680, code="11680", name="강남구", type="district", center_lat=37.517236, center_lng=127.047325, unit_cnt_sum=124000),
    Region(id=11650, code="11650", name="서초구", type="district", center_lat=37.483712, center_lng=127.032411, unit_cnt_sum=98000),
    Region(id=11710, code="11710", name="송파구", type="district", center_lat=37.514544, center_lng=127.105922, unit_cnt_sum=142000),
  ])
  session.add_all([
    Complex(id=1001, region_id=11680, parcel_id=9001001, pnu="1168010600106330000", name="래미안대치팰리스", trade_name="래미안대치팰리스", address="서울특별시 강남구 대치동 633", latitude=37.497953, longitude=127.058064, dong_cnt=13, unit_cnt=1608, use_date="2015-09-18"),
    Complex(id=1002, region_id=11680, parcel_id=9001002, pnu="1168010700104670000", name="압구정현대", trade_name="현대아파트", address="서울특별시 강남구 압구정동 467", latitude=37.531884, longitude=127.028751, dong_cnt=83, unit_cnt=3130, use_date="1976-06-07"),
    Complex(id=1003, region_id=11650, parcel_id=9002001, pnu="1165010800116880000", name="반포자이", trade_name="반포자이", address="서울특별시 서초구 반포동 20-43", latitude=37.507074, longitude=127.014592, dong_cnt=44, unit_cnt=3410, use_date="2009-03-31"),
    Complex(id=1004, region_id=11710, parcel_id=9003001, pnu="1171010100100190000", name="잠실엘스", trade_name="잠실엘스", address="서울특별시 송파구 잠실동 19", latitude=37.513346, longitude=127.083151, dong_cnt=72, unit_cnt=5678, use_date="2008-09-30"),
    Complex(id=1005, region_id=11680, parcel_id=9001003, pnu="1168010300100000000", name="좌표없는강남단지", trade_name="좌표없는강남단지", address="서울특별시 강남구 개포동", latitude=None, longitude=None, dong_cnt=4, unit_cnt=320, use_date="1999-01-12"),
  ])
  session.add_all([
    Trade(id=5001, complex_id=1001, deal_date="2025-12-15", deal_amount=405000, excl_area=84.97, floor=12, apt_dong="101"),
    Trade(id=5002, complex_id=1001, deal_date="2026-01-10", deal_amount=420000, excl_area=84.97, floor=18, apt_dong="102"),
    Trade(id=5003, complex_id=1001, deal_date="2026-01-28", deal_amount=435000, excl_area=114.14, floor=9, apt_dong="103"),
    Trade(id=5004, complex_id=1002, deal_date="2025-11-20", deal_amount=510000, excl_area=131.48, floor=8, apt_dong="10"),
    Trade(id=5005, complex_id=1002, deal_date="2026-02-05", deal_amount=528000, excl_area=131.48, floor=11, apt_dong="11"),
    Trade(id=5006, complex_id=1003, deal_date="2026-01-21", deal_amount=395000, excl_area=84.94, floor=17, apt_dong="110"),
    Trade(id=5007, complex_id=1003, deal_date="2026-03-02", deal_amount=610000, excl_area=165.05, floor=20, apt_dong="210"),
    Trade(id=5008, complex_id=1004, deal_date="2026-02-14", deal_amount=310000, excl_area=84.80, floor=15, apt_dong="117"),
    Trade(id=5009, complex_id=1004, deal_date="2026-03-19", deal_amount=330000, excl_area=84.80, floor=21, apt_dong="118"),
    Trade(id=5010, complex_id=1005, deal_date="2026-01-05", deal_amount=180000, excl_area=59.97, floor=7, apt_dong="1"),
  ])
