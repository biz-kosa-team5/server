"""H1 단순조회 DTO·Policy·DAO·Service 핵심 동작 테스트."""

from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import Base, Complex, Region, Trade
from app.simple_lookup import (
  LocationData,
  SimpleLookupDao,
  SimpleLookupPolicyError,
  SimpleLookupQueryType,
  SimpleLookupResult,
  SimpleLookupService,
  SimpleLookupSlots,
  SimpleLookupTargetError,
  TradeData,
  estimate_exclusive_area,
  normalize_simple_lookup_policy,
  parse_period,
  resolve_complex_target,
  resolve_nearest_actual_area,
)
from app.simple_lookup.policy import subtract_calendar_period


def make_session() -> Session:
  """각 테스트가 독립적으로 사용할 작은 인메모리 DB를 만든다."""

  engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
  )
  Base.metadata.create_all(engine)
  session = Session(engine)
  session.add(
    Region(
      id=1,
      code="1",
      name="테스트구",
      type="district",
      center_lat=37.5,
      center_lng=127.0,
    )
  )
  session.add_all([
    Complex(
      id=101,
      region_id=1,
      parcel_id=1001,
      name="잠실엘스",
      trade_name="잠실엘스",
      address="서울 송파구 잠실동",
      latitude=37.5,
      longitude=127.1,
    ),
    Complex(
      id=102,
      region_id=1,
      parcel_id=1002,
      name="현대아파트 1차",
      trade_name="현대아파트",
      address="서울 강남구",
    ),
    Complex(
      id=103,
      region_id=1,
      parcel_id=1003,
      name="현대아파트 2차",
      trade_name="현대아파트",
      address="서울 구로구",
    ),
    Complex(
      id=104,
      region_id=1,
      parcel_id=1004,
      name="위치정보없는단지",
      trade_name="위치정보없는단지",
    ),
    Complex(
      id=105,
      region_id=1,
      parcel_id=1005,
      name="테스트_100%아파트",
      trade_name="테스트_100%아파트",
      address="서울 테스트구",
    ),
  ])
  session.add_all([
    Trade(id=1, complex_id=101, deal_date="2025-01-10", deal_amount=200000, excl_area=84.8, floor=10),
    Trade(id=2, complex_id=101, deal_date="2025-02-10", deal_amount=210000, excl_area=84.8, floor=12),
    Trade(id=3, complex_id=101, deal_date="2025-03-10", deal_amount=190000, excl_area=59.9, floor=8),
  ])
  session.commit()
  return session


def assert_policy_error(reason: str, callback) -> SimpleLookupPolicyError:
  with pytest.raises(SimpleLookupPolicyError) as captured:
    callback()
  assert captured.value.reason == reason
  return captured.value


# DTO

def test_slots_accept_valid_input_and_reject_contract_errors():
  slots = SimpleLookupSlots(
    query_type=SimpleLookupQueryType.TRADE_HISTORY,
    complex_name="반포자이",
    pyeong=34,
    period="1y",
    limit=5,
  )
  assert slots.query_type == "trade_history"

  invalid_payloads = [
    {"query_type": "price", "complex_name": "반포자이"},
    {"query_type": "location", "complex_name": "반포자이", "unknown_slot": "오타"},
    {"query_type": "trade_history", "complex_name": "반포자이", "area": True},
    {"query_type": "trade_history", "complex_name": "반포자이", "limit": True},
  ]
  for payload in invalid_payloads:
    with pytest.raises(ValidationError):
      SimpleLookupSlots(**payload)


def test_result_uses_one_list_shape_for_all_query_types():
  location = SimpleLookupResult(
    success=True,
    query_type="location",
    data=[LocationData(complex_id=101, complex_name="잠실엘스")],
  )
  trades = SimpleLookupResult(
    success=True,
    query_type="trade_history",
    data=[
      TradeData(
        trade_id=1,
        deal_date="2025-01-10",
        deal_amount=200000,
        exclusive_area=84.8,
      )
    ],
  )

  assert isinstance(location.data[0], LocationData)
  assert isinstance(trades.data[0], TradeData)
  assert trades.data[0].deal_amount_unit == "만원"


# Policy

def test_location_records_valid_unused_slots_and_rejects_invalid_ones():
  normalized = normalize_simple_lookup_policy(
    SimpleLookupSlots(
      query_type="location",
      complex_name="  잠실엘스  ",
      pyeong=34,
      period="1y",
    )
  )
  assert normalized.criteria == {"complex_name": "잠실엘스"}
  assert normalized.ignored_slots == {"pyeong": 34, "period": "1y"}

  invalid_slots = [
    {"period": "banana"},
    {"start_date": "not-a-date"},
    {"start_date": "2025-12-31", "end_date": "2025-01-01"},
    {"period": "1y", "start_date": "2025-01-01"},
    {"limit": 0},
  ]
  for values in invalid_slots:
    slots = SimpleLookupSlots(
      query_type="location",
      complex_name="잠실엘스",
      **values,
    )
    assert_policy_error(
      "invalid_request",
      lambda slots=slots: normalize_simple_lookup_policy(slots),
    )


def test_area_and_limit_are_normalized_for_trade_history():
  normalized = normalize_simple_lookup_policy(
    SimpleLookupSlots(
      query_type="trade_history",
      complex_name="잠실엘스",
      area=84,
      limit=100,
    )
  )
  assert normalized.criteria["area_min"] == 83
  assert normalized.criteria["area_max"] == 85
  assert normalized.criteria["limit"] == 20


def test_conflicting_area_and_pyeong_are_invalid():
  slots = SimpleLookupSlots(
    query_type="trade_history",
    complex_name="잠실엘스",
    area=84,
    pyeong=34,
  )
  assert_policy_error(
    "invalid_request",
    lambda: normalize_simple_lookup_policy(slots),
  )


def test_pyeong_and_pyeong_range_are_converted_without_fixed_size_limits():
  single = normalize_simple_lookup_policy(
    SimpleLookupSlots(
      query_type="trade_history",
      complex_name="잠실엘스",
      pyeong=110,
    )
  )
  area_range = normalize_simple_lookup_policy(
    SimpleLookupSlots(
      query_type="trade_history",
      complex_name="잠실엘스",
      pyeong_min=15,
      pyeong_max=110,
    )
  )

  assert single.criteria["estimated_exclusive_area"] == estimate_exclusive_area(110)
  assert area_range.criteria["area_min"] == estimate_exclusive_area(15)
  assert area_range.criteria["area_max"] == estimate_exclusive_area(110)


def test_nearest_actual_area_selects_closest_and_prefers_smaller_tie():
  closest = resolve_nearest_actual_area(
    estimate_exclusive_area(34),
    [59.9, 84.8, 114.1],
  )
  tied = resolve_nearest_actual_area(84.3, [85.0, 83.6])

  assert closest["selected_exclusive_area"] == 84.8
  assert tied["selected_exclusive_area"] == 83.6


def test_record_high_rejects_multiple_results():
  slots = SimpleLookupSlots(
    query_type="record_high",
    complex_name="잠실엘스",
    limit=2,
  )
  assert_policy_error(
    "unsupported_request",
    lambda: normalize_simple_lookup_policy(slots),
  )


def test_dynamic_period_and_explicit_date_priority():
  period = normalize_simple_lookup_policy(
    SimpleLookupSlots(
      query_type="trade_history",
      complex_name="잠실엘스",
      period="2m",
    ),
    base_date=date(2025, 3, 31),
  )
  explicit = normalize_simple_lookup_policy(
    SimpleLookupSlots(
      query_type="trade_history",
      complex_name="잠실엘스",
      period="1y",
      start_date="2025-01-01",
      end_date="2025-02-28",
    ),
    base_date="2025-03-31",
  )

  assert period.criteria["start_date"] == "2025-01-31"
  assert explicit.criteria["period"] is None
  assert explicit.ignored_slots == {"period": "1y"}


def test_period_format_range_month_end_and_leap_year():
  assert parse_period("8m") == ("month", 8)
  assert parse_period("2y") == ("year", 2)
  assert subtract_calendar_period(date(2026, 3, 31), "1m") == date(2026, 2, 28)
  assert subtract_calendar_period(date(2024, 2, 29), "1y") == date(2023, 2, 28)

  for value in ("0m", "1.5y", "2d"):
    assert_policy_error("invalid_request", lambda value=value: parse_period(value))
  assert_policy_error("unsupported_request", lambda: parse_period("181m"))


# DAO와 단지 확정

def test_complex_search_supports_exact_partial_and_ambiguous_results():
  with make_session() as session:
    dao = SimpleLookupDao(session)

    assert [row.id for row in dao.find_exact_complexes("잠실 엘스")] == [101]
    assert resolve_complex_target(dao, "잠실").id == 101

    with pytest.raises(SimpleLookupTargetError) as captured:
      resolve_complex_target(dao, "현대아파트")
    assert captured.value.reason == "ambiguous_target"
    assert [item["complex_id"] for item in captured.value.candidates] == [102, 103]


def test_partial_search_escapes_like_wildcards():
  with make_session() as session:
    dao = SimpleLookupDao(session)

    assert [row.id for row in dao.find_partial_complexes("_100%")] == [105]
    assert [row.id for row in dao.find_partial_complexes("%")] == [105]


def test_target_not_found_is_reported():
  with make_session() as session:
    with pytest.raises(SimpleLookupTargetError) as captured:
      resolve_complex_target(SimpleLookupDao(session), "없는아파트")
    assert captured.value.reason == "target_not_found"


def test_dao_returns_base_date_distinct_areas_and_filtered_history():
  with make_session() as session:
    dao = SimpleLookupDao(session)

    assert dao.find_max_deal_date() == "2025-03-10"
    assert dao.find_distinct_areas(101) == [59.9, 84.8]
    rows = dao.find_trade_history(
      101,
      {
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "area_min": 83,
        "area_max": 85,
        "limit": 1,
      },
    )
    assert [row.id for row in rows] == [2]


def test_dao_record_high_returns_highest_amount():
  with make_session() as session:
    row = SimpleLookupDao(session).find_record_high(
      101,
      {"area_min": 83, "area_max": 85},
    )
    assert row is not None
    assert row.id == 2


# Service

def test_service_location_success_and_missing_location():
  with make_session() as session:
    service = SimpleLookupService(SimpleLookupDao(session))

    success = service.handle(
      SimpleLookupSlots(query_type="location", complex_name="잠실 엘스")
    )
    failure = service.handle(
      SimpleLookupSlots(query_type="location", complex_name="위치정보없는단지")
    )

    assert success.success is True
    assert isinstance(success.data[0], LocationData)
    assert failure.success is False
    assert failure.reason == "no_result"


def test_service_trade_history_matches_pyeong_and_record_high_returns_one_item():
  with make_session() as session:
    service = SimpleLookupService(SimpleLookupDao(session))

    history = service.handle(
      SimpleLookupSlots(
        query_type="trade_history",
        complex_name="잠실엘스",
        pyeong=34,
      )
    )
    high = service.handle(
      SimpleLookupSlots(query_type="record_high", complex_name="잠실엘스")
    )

    assert [item.trade_id for item in history.data] == [2, 1]
    assert history.criteria["selected_exclusive_area"] == 84.8
    assert len(high.data) == 1
    assert high.data[0].trade_id == 2


def test_service_uses_injected_base_date_and_avoids_location_date_query():
  with make_session() as session:
    injected = SimpleLookupService(
      SimpleLookupDao(session),
      base_date="2025-03-10",
    )
    period_result = injected.handle(
      SimpleLookupSlots(
        query_type="trade_history",
        complex_name="잠실엘스",
        period="2m",
      )
    )
    assert period_result.criteria["start_date"] == "2025-01-10"

    dao = SimpleLookupDao(session)

    def unexpected_date_query():
      raise AssertionError("location은 base_date를 조회하면 안 됩니다.")

    dao.find_max_deal_date = unexpected_date_query
    location = SimpleLookupService(dao).handle(
      SimpleLookupSlots(
        query_type="location",
        complex_name="잠실엘스",
        period="1y",
      )
    )
    assert location.success is True
    assert location.ignored_slots == {"period": "1y"}


def test_service_converts_business_errors_to_result():
  with make_session() as session:
    service = SimpleLookupService(SimpleLookupDao(session))

    invalid = service.handle(
      SimpleLookupSlots(
        query_type="trade_history",
        complex_name="잠실엘스",
        area=84,
        pyeong=34,
      )
    )
    ambiguous = service.handle(
      SimpleLookupSlots(query_type="location", complex_name="현대아파트")
    )

    assert invalid.reason == "invalid_request"
    assert ambiguous.reason == "ambiguous_target"
    assert len(ambiguous.candidates) == 2


def test_service_returns_no_result_and_preserves_criteria():
  with make_session() as session:
    service = SimpleLookupService(
      SimpleLookupDao(session),
      base_date="2025-03-10",
    )
    result = service.handle(
      SimpleLookupSlots(
        query_type="trade_history",
        complex_name="잠실엘스",
        start_date="2024-01-01",
        end_date="2024-12-31",
      )
    )

    assert result.reason == "no_result"
    assert result.data == []
    assert result.criteria["complex_id"] == 101


def test_service_does_not_hide_database_errors():
  with make_session() as session:
    service = SimpleLookupService(SimpleLookupDao(session))

    def broken_search(_complex_name: str):
      raise RuntimeError("database unavailable")

    service.dao.find_exact_complexes = broken_search

    with pytest.raises(RuntimeError, match="database unavailable"):
      service.handle(
        SimpleLookupSlots(query_type="location", complex_name="잠실엘스")
      )
