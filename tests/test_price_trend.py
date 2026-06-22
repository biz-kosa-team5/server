"""H4 시세추이 핸들러의 DTO 계약 테스트."""

from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.chatbot.features.price_trend import (
  PriceTrendDao,
  PriceChangeRankingItem,
  PriceRankingItem,
  TrendPoint,
  TrendResult,
  TrendService,
  TrendSlots,
  TrendPolicyError,
  TrendTargetError,
  normalize_trend_policy,
  resolve_complex_target,
  resolve_nearest_actual_area,
  resolve_region_scope_ids,
  resolve_region_target,
  resolve_region_targets,
)
from app.models import Base, Complex, Region, Trade


def test_trend_slots_accept_all_supported_query_types():
  """상위 에이전트가 네 가지 H4 조회 유형을 전달할 수 있다."""

  query_types = [
    "complex_trend",
    "region_trend",
    "price_change_ranking",
    "price_ranking",
  ]

  for query_type in query_types:
    slots = TrendSlots(query_type=query_type)
    assert slots.query_type == query_type


def test_trend_slots_reject_contract_errors():
  """잘못된 query_type, 미정의 슬롯, boolean 숫자는 즉시 거부한다."""

  invalid_payloads = [
    {"query_type": "unknown_trend"},
    {"query_type": "complex_trend", "unknown_slot": "오타"},
    {"query_type": "region_trend", "area": True},
    {"query_type": "price_ranking", "limit": False},
  ]

  for payload in invalid_payloads:
    with pytest.raises(ValidationError):
      TrendSlots(**payload)


def test_trend_result_uses_one_list_shape_for_all_result_types():
  """시계열과 두 순위 결과가 모두 같은 data 리스트에 담긴다."""

  trend_point = TrendPoint(
    period_start="2026-01-01",
    avg_deal_amount=200000,
    avg_price_per_sqm=2358.49,
    min_deal_amount=190000,
    max_deal_amount=210000,
    trade_count=3,
    avg_exclusive_area=84.8,
  )
  change_item = PriceChangeRankingItem(
    rank=1,
    complex_id=101,
    complex_name="테스트아파트",
    start_avg_price_per_sqm=2000,
    end_avg_price_per_sqm=2200,
    change_amount=200,
    change_rate=10,
    start_trade_count=2,
    end_trade_count=3,
    avg_exclusive_area=84.8,
  )
  ranking_item = PriceRankingItem(
    rank=1,
    complex_id=101,
    complex_name="테스트아파트",
    trade_id=1,
    deal_date="2026-05-01",
    deal_amount=220000,
    exclusive_area=84.8,
  )

  trend_result = TrendResult(
    success=True,
    query_type="complex_trend",
    data=[trend_point],
  )
  change_result = TrendResult(
    success=True,
    query_type="price_change_ranking",
    data=[change_item],
  )
  ranking_result = TrendResult(
    success=True,
    query_type="price_ranking",
    data=[ranking_item],
  )

  assert isinstance(trend_result.data[0], TrendPoint)
  assert isinstance(change_result.data[0], PriceChangeRankingItem)
  assert isinstance(ranking_result.data[0], PriceRankingItem)
  assert trend_result.data[0].deal_amount_unit == "만원"
  assert change_result.data[0].price_per_sqm_unit == "만원/㎡"
  assert ranking_result.data[0].deal_amount_unit == "만원"


def assert_policy_error(reason: str, callback) -> TrendPolicyError:
  """Policy 오류 코드와 예외 발생을 함께 확인한다."""

  with pytest.raises(TrendPolicyError) as captured:
    callback()
  assert captured.value.reason == reason
  return captured.value


# Policy

def test_query_type_requires_the_correct_target():
  """단지 추이는 단지명, 나머지 조회는 지역명이 필요하다."""

  complex_policy = normalize_trend_policy(
    TrendSlots(query_type="complex_trend", complex_name="  래미안  대치팰리스 "),
    base_date=date(2026, 6, 1),
  )
  region_policy = normalize_trend_policy(
    TrendSlots(query_type="region_trend", region_names=[" 강남구 ", "서초구", "강남구"]),
    base_date=date(2026, 6, 1),
  )

  assert complex_policy.criteria["complex_name"] == "래미안 대치팰리스"
  assert region_policy.criteria["region_names"] == ["강남구", "서초구"]

  invalid_slots = [
    TrendSlots(query_type="complex_trend"),
    TrendSlots(query_type="region_trend"),
    TrendSlots(
      query_type="price_ranking",
      complex_name="래미안",
      region_name="강남구",
    ),
  ]
  for slots in invalid_slots:
    assert_policy_error(
      "invalid_request",
      lambda slots=slots: normalize_trend_policy(
        slots,
        base_date=date(2026, 6, 1),
      ),
    )


def test_query_types_apply_default_period_interval_and_ranking_options():
  """조회 유형별 기본 기간과 정렬 조건이 자동 적용된다."""

  complex_trend = normalize_trend_policy(
    TrendSlots(query_type="complex_trend", complex_name="래미안"),
    base_date="2026-06-01",
  )
  change_ranking = normalize_trend_policy(
    TrendSlots(query_type="price_change_ranking", region_name="강남구"),
    base_date="2026-06-01",
  )
  price_ranking = normalize_trend_policy(
    TrendSlots(query_type="price_ranking", region_name="강남구"),
  )

  assert complex_trend.criteria["period"] == "3y"
  assert complex_trend.criteria["start_date"] == "2023-06-01"
  assert complex_trend.criteria["interval"] == "quarter"

  assert change_ranking.criteria["period"] == "1y"
  assert change_ranking.criteria["change_direction"] == "up"
  assert change_ranking.criteria["window_months"] == 3
  assert change_ranking.criteria["limit"] == 5

  assert price_ranking.criteria["date_scope"] == "all_data"
  assert price_ranking.criteria["rank_order"] == "highest"
  assert price_ranking.criteria["limit"] == 5


def test_period_interval_direction_order_and_limit_are_validated():
  """지원하지 않는 정책값은 DAO까지 전달하지 않는다."""

  invalid_slots = [
    TrendSlots(
      query_type="complex_trend",
      complex_name="래미안",
      period="0m",
    ),
    TrendSlots(
      query_type="region_trend",
      region_name="강남구",
      interval="week",
    ),
    TrendSlots(
      query_type="price_change_ranking",
      region_name="강남구",
      change_direction="increase",
    ),
    TrendSlots(
      query_type="price_ranking",
      region_name="강남구",
      rank_order="desc",
    ),
    TrendSlots(
      query_type="price_ranking",
      region_name="강남구",
      limit=0,
    ),
  ]

  for slots in invalid_slots:
    assert_policy_error(
      "invalid_request",
      lambda slots=slots: normalize_trend_policy(
        slots,
        base_date="2026-06-01",
      ),
    )

  limited = normalize_trend_policy(
    TrendSlots(
      query_type="price_ranking",
      region_name="강남구",
      limit=100,
    )
  )
  assert limited.criteria["limit"] == 20


def test_area_and_pyeong_use_different_complex_and_region_policies():
  """단지의 단일 평형만 실제 거래 면적 확정 단계로 넘긴다."""

  direct_area = normalize_trend_policy(
    TrendSlots(
      query_type="region_trend",
      region_name="강남구",
      area=84,
    ),
    base_date="2026-06-01",
  )
  complex_pyeong = normalize_trend_policy(
    TrendSlots(
      query_type="complex_trend",
      complex_name="래미안",
      pyeong=34,
    ),
    base_date="2026-06-01",
  )
  region_pyeong = normalize_trend_policy(
    TrendSlots(
      query_type="region_trend",
      region_name="강남구",
      pyeong=34,
    ),
    base_date="2026-06-01",
  )

  assert direct_area.criteria["area_min"] == 83
  assert direct_area.criteria["area_max"] == 85
  assert direct_area.criteria["primary_metric"] == "avg_deal_amount"

  assert complex_pyeong.criteria["area_match_policy"] == "nearest_actual_exclusive_area"
  assert "area_min" not in complex_pyeong.criteria

  estimated = region_pyeong.criteria["estimated_exclusive_area"]
  assert region_pyeong.criteria["area_min"] == pytest.approx(estimated - 1)
  assert region_pyeong.criteria["area_max"] == pytest.approx(estimated + 1)


def test_nearest_actual_area_and_change_windows_follow_policy():
  """평형의 실제 면적 선택과 변화율 비교 window를 확인한다."""

  selected = resolve_nearest_actual_area(84.0, [59.9, 84.2, 114.8])
  assert selected["selected_exclusive_area"] == 84.2

  policy = normalize_trend_policy(
    TrendSlots(
      query_type="price_change_ranking",
      region_name="강남구",
      period="1y",
    ),
    base_date="2026-03-19",
  )
  assert policy.criteria["start_window_start"] == "2025-03-19"
  assert policy.criteria["start_window_end"] == "2025-06-18"
  assert policy.criteria["end_window_start"] == "2025-12-20"
  assert policy.criteria["end_window_end"] == "2026-03-19"
  assert policy.criteria["min_trade_count"] == 2


def test_change_ranking_rejects_overlapping_comparison_windows():
  """짧은 조회 기간에서 시작·종료 window가 겹치면 비교하지 않는다."""

  assert_policy_error(
    "invalid_request",
    lambda: normalize_trend_policy(
      TrendSlots(
        query_type="price_change_ranking",
        region_name="강남구",
        period="1m",
      ),
      base_date="2026-03-19",
    ),
  )


def test_unused_valid_slots_are_recorded_but_invalid_values_are_rejected():
  """현재 조회에서 사용하지 않는 정상 슬롯은 추적 가능하게 남긴다."""

  normalized = normalize_trend_policy(
    TrendSlots(
      query_type="complex_trend",
      complex_name="래미안",
      rank_order="lowest",
      limit=3,
    ),
    base_date="2026-06-01",
  )
  assert normalized.ignored_slots == {
    "rank_order": "lowest",
    "limit": 3,
  }

  assert_policy_error(
    "invalid_request",
    lambda: normalize_trend_policy(
      TrendSlots(
        query_type="price_ranking",
        region_name="강남구",
        interval="week",
      )
    ),
  )


# DAO / Target

def make_target_session() -> Session:
  """대상 검색 테스트에 사용할 작은 지역·단지 DB를 만든다."""

  engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
  )
  Base.metadata.create_all(engine)
  session = Session(engine)

  session.add_all([
    Region(
      id=1,
      code="SEOUL",
      name="서울특별시",
      type="city",
      center_lat=37.5665,
      center_lng=126.9780,
    ),
    Region(
      id=2,
      code="GANGNAM",
      name="강남구",
      type="district",
      parent_id=1,
      center_lat=37.5172,
      center_lng=127.0473,
    ),
    Region(
      id=3,
      code="DAECHI",
      name="대치동",
      type="neighborhood",
      parent_id=2,
      center_lat=37.4930,
      center_lng=127.0567,
    ),
    Region(
      id=4,
      code="GANGDONG",
      name="강동구",
      type="district",
      parent_id=1,
      center_lat=37.5301,
      center_lng=127.1238,
    ),
    Region(
      id=5,
      code="TEST_A",
      name="테스트동",
      type="neighborhood",
      parent_id=2,
      center_lat=37.5000,
      center_lng=127.0500,
    ),
    Region(
      id=6,
      code="TEST_B",
      name="테스트동",
      type="neighborhood",
      parent_id=4,
      center_lat=37.5400,
      center_lng=127.1300,
    ),
  ])
  session.add_all([
    Complex(
      id=101,
      region_id=3,
      parcel_id=1001,
      name="래미안 대치팰리스",
      trade_name="래미안대치팰리스",
      address="서울 강남구 대치동",
    ),
    Complex(
      id=102,
      region_id=3,
      parcel_id=1002,
      name="현대아파트 1차",
      trade_name="현대아파트",
      address="서울 강남구",
    ),
    Complex(
      id=103,
      region_id=4,
      parcel_id=1003,
      name="현대아파트 2차",
      trade_name="현대아파트",
      address="서울 강동구",
    ),
    Complex(
      id=104,
      region_id=3,
      parcel_id=1004,
      name="테스트_100%아파트",
      trade_name="테스트_100%아파트",
      address="서울 강남구",
    ),
  ])
  session.add_all([
    Trade(
      id=1001,
      complex_id=101,
      deal_date="2025-01-10",
      deal_amount=200000,
      excl_area=84.8,
      floor=10,
    ),
    Trade(
      id=1002,
      complex_id=101,
      deal_date="2025-02-10",
      deal_amount=220000,
      excl_area=84.8,
      floor=12,
    ),
    Trade(
      id=1003,
      complex_id=101,
      deal_date="2025-04-10",
      deal_amount=240000,
      excl_area=114.0,
      floor=15,
    ),
    Trade(
      id=1004,
      complex_id=102,
      deal_date="2025-01-20",
      deal_amount=300000,
      excl_area=84.9,
      floor=8,
    ),
    Trade(
      id=1005,
      complex_id=103,
      deal_date="2025-01-25",
      deal_amount=180000,
      excl_area=59.9,
      floor=7,
    ),
    Trade(
      id=1006,
      complex_id=102,
      deal_date="2025-03-20",
      deal_amount=280000,
      excl_area=84.9,
      floor=5,
    ),
  ])
  session.commit()
  return session


def assert_target_error(reason: str, callback) -> TrendTargetError:
  """대상 확정 실패 코드와 예외 발생을 함께 확인한다."""

  with pytest.raises(TrendTargetError) as captured:
    callback()
  assert captured.value.reason == reason
  return captured.value


def test_complex_target_uses_exact_then_partial_search():
  """단지 검색은 정확 일치를 우선하고 후보 한 곳만 확정한다."""

  session = make_target_session()
  try:
    dao = PriceTrendDao(session)

    exact = resolve_complex_target(dao, " 래미안대치 팰리스 ")
    partial = resolve_complex_target(dao, "대치팰리스")

    assert exact.id == 101
    assert partial.id == 101
  finally:
    session.close()


def test_complex_target_returns_ambiguous_and_not_found_errors():
  """동명 단지는 후보 목록을 반환하고 없는 단지는 실패한다."""

  session = make_target_session()
  try:
    dao = PriceTrendDao(session)

    ambiguous = assert_target_error(
      "ambiguous_target",
      lambda: resolve_complex_target(dao, "현대아파트"),
    )
    not_found = assert_target_error(
      "target_not_found",
      lambda: resolve_complex_target(dao, "없는아파트"),
    )

    assert [row["complex_id"] for row in ambiguous.candidates] == [102, 103]
    assert not not_found.candidates
  finally:
    session.close()


def test_partial_search_escapes_like_wildcards():
  """단지명 속 밑줄과 퍼센트 기호를 LIKE 문법으로 오해하지 않는다."""

  session = make_target_session()
  try:
    dao = PriceTrendDao(session)
    target = resolve_complex_target(dao, "테스트_100%")
    assert target.id == 104
  finally:
    session.close()


def test_region_target_supports_single_multiple_and_ambiguous_names():
  """단일·복수 지역을 확정하고 동명 지역은 임의로 선택하지 않는다."""

  session = make_target_session()
  try:
    dao = PriceTrendDao(session)

    gangnam = resolve_region_target(dao, " 강남구 ")
    regions = resolve_region_targets(dao, ["강남구", "강동구", "강남구"])
    ambiguous = assert_target_error(
      "ambiguous_target",
      lambda: resolve_region_target(dao, "테스트동"),
    )

    assert gangnam.id == 2
    assert [region.id for region in regions] == [2, 4]
    assert [row["region_id"] for row in ambiguous.candidates] == [5, 6]
  finally:
    session.close()


def test_region_scope_uses_selected_region_ids_directly():
  """현재 DB 구조에서는 확정한 구 ID를 조회 조건으로 그대로 사용한다."""

  session = make_target_session()
  try:
    dao = PriceTrendDao(session)
    gangnam = resolve_region_target(dao, "강남구")
    scope_ids = resolve_region_scope_ids([gangnam])

    assert scope_ids == [2]
  finally:
    session.close()


def test_complex_trend_groups_trades_by_month():
  """특정 단지 거래를 월별 시계열로 집계한다."""

  session = make_target_session()
  try:
    dao = PriceTrendDao(session)
    rows = dao.find_complex_trend(
      101,
      {
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "interval": "month",
      },
    )

    assert [row["period_start"] for row in rows] == [
      "2025-01-01",
      "2025-02-01",
      "2025-04-01",
    ]
    assert rows[0]["avg_deal_amount"] == 200000
    assert rows[0]["trade_count"] == 1
    assert rows[0]["avg_price_per_sqm"] == pytest.approx(2358.49)
  finally:
    session.close()


def test_complex_trend_groups_by_quarter_and_applies_area_filter():
  """분기 집계와 전용면적 조건이 함께 적용된다."""

  session = make_target_session()
  try:
    dao = PriceTrendDao(session)
    rows = dao.find_complex_trend(
      101,
      {
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "interval": "quarter",
        "area_min": 83,
        "area_max": 85,
      },
    )

    assert len(rows) == 1
    assert rows[0]["period_start"] == "2025-01-01"
    assert rows[0]["avg_deal_amount"] == 210000
    assert rows[0]["min_deal_amount"] == 200000
    assert rows[0]["max_deal_amount"] == 220000
    assert rows[0]["trade_count"] == 2
  finally:
    session.close()


def test_region_trend_combines_complexes_in_selected_regions():
  """선택한 지역에 직접 연결된 여러 단지 거래를 함께 집계한다."""

  session = make_target_session()
  try:
    dao = PriceTrendDao(session)
    rows = dao.find_region_trend(
      [3],
      {
        "start_date": "2025-01-01",
        "end_date": "2025-01-31",
        "interval": "month",
      },
    )

    # region_id=3에는 101과 102 두 단지가 직접 연결되어 있다.
    assert len(rows) == 1
    assert rows[0]["period_start"] == "2025-01-01"
    assert rows[0]["avg_deal_amount"] == 250000
    assert rows[0]["trade_count"] == 2
  finally:
    session.close()


def test_trend_support_queries_base_date_and_actual_areas():
  """기간 계산과 단일 평형 확정에 필요한 보조 조회를 확인한다."""

  session = make_target_session()
  try:
    dao = PriceTrendDao(session)

    assert dao.find_max_deal_date() == "2025-04-10"
    assert dao.find_distinct_areas(101) == [84.8, 114.0]
  finally:
    session.close()


def test_price_ranking_selects_one_representative_trade_per_complex():
  """같은 단지의 거래가 여러 건이어도 순위에는 대표 거래 한 건만 나온다."""

  session = make_target_session()
  try:
    dao = PriceTrendDao(session)

    highest = dao.find_price_ranking(
      [3],
      {
        "rank_order": "highest",
        "limit": 5,
        "start_date": None,
        "end_date": None,
      },
    )
    lowest = dao.find_price_ranking(
      [3],
      {
        "rank_order": "lowest",
        "limit": 5,
        "start_date": None,
        "end_date": None,
      },
    )

    # region_id=3에는 단지 101과 102가 있으며 각 단지가 한 번씩만 나온다.
    assert [row["complex_id"] for row in highest] == [102, 101]
    assert [row["deal_amount"] for row in highest] == [300000, 240000]
    assert [row["rank"] for row in highest] == [1, 2]

    assert [row["complex_id"] for row in lowest] == [101, 102]
    assert [row["deal_amount"] for row in lowest] == [200000, 280000]
  finally:
    session.close()


def test_price_ranking_applies_period_area_and_limit():
  """대표 거래를 선택하기 전에 기간·면적 조건과 최대 개수를 적용한다."""

  session = make_target_session()
  try:
    dao = PriceTrendDao(session)
    rows = dao.find_price_ranking(
      [3],
      {
        "rank_order": "highest",
        "limit": 1,
        "start_date": "2025-01-01",
        "end_date": "2025-02-28",
        "area_min": 84,
        "area_max": 85,
      },
    )

    assert len(rows) == 1
    assert rows[0]["complex_id"] == 102
    assert rows[0]["trade_id"] == 1004
    assert rows[0]["deal_amount"] == 300000
  finally:
    session.close()


def make_change_ranking_session() -> Session:
  """가격 변화율 순위의 시작·종료 window 테스트 데이터를 만든다."""

  session = make_target_session()
  session.add_all([
    Complex(
      id=105,
      region_id=2,
      parcel_id=1005,
      name="상승아파트",
      trade_name="상승아파트",
      address="서울 강남구",
    ),
    Complex(
      id=106,
      region_id=2,
      parcel_id=1006,
      name="하락아파트",
      trade_name="하락아파트",
      address="서울 강남구",
    ),
    Complex(
      id=107,
      region_id=2,
      parcel_id=1007,
      name="거래부족아파트",
      trade_name="거래부족아파트",
      address="서울 강남구",
    ),
  ])
  session.add_all([
    # 시작 window: 2025-01-01~2025-03-31
    # 종료 window: 2025-10-01~2025-12-31
    Trade(id=2001, complex_id=105, deal_date="2025-01-10", deal_amount=100000, excl_area=100),
    Trade(id=2002, complex_id=105, deal_date="2025-02-10", deal_amount=100000, excl_area=100),
    Trade(id=2003, complex_id=105, deal_date="2025-10-10", deal_amount=120000, excl_area=100),
    Trade(id=2004, complex_id=105, deal_date="2025-11-10", deal_amount=120000, excl_area=100),
    Trade(id=2005, complex_id=106, deal_date="2025-01-15", deal_amount=100000, excl_area=100),
    Trade(id=2006, complex_id=106, deal_date="2025-02-15", deal_amount=100000, excl_area=100),
    Trade(id=2007, complex_id=106, deal_date="2025-10-15", deal_amount=80000, excl_area=100),
    Trade(id=2008, complex_id=106, deal_date="2025-11-15", deal_amount=80000, excl_area=100),
    # 시작·종료 각각 한 건뿐이므로 기본 최소 거래 2건을 충족하지 못한다.
    Trade(id=2009, complex_id=107, deal_date="2025-01-20", deal_amount=100000, excl_area=100),
    Trade(id=2010, complex_id=107, deal_date="2025-10-20", deal_amount=150000, excl_area=100),
  ])
  session.commit()
  return session


def change_ranking_criteria(direction: str = "up") -> dict:
  """DAO 테스트에서 공통으로 사용할 변화율 비교 조건."""

  return {
    "start_window_start": "2025-01-01",
    "start_window_end": "2025-03-31",
    "end_window_start": "2025-10-01",
    "end_window_end": "2025-12-31",
    "min_trade_count": 2,
    "change_direction": direction,
    "limit": 5,
  }


def test_price_change_ranking_supports_up_down_and_absolute():
  """상승·하락·절대변동 방향에 따라 단지 변화율을 정렬한다."""

  session = make_change_ranking_session()
  try:
    dao = PriceTrendDao(session)

    up_result = dao.find_price_change_ranking([2], change_ranking_criteria("up"))
    down_result = dao.find_price_change_ranking([2], change_ranking_criteria("down"))
    absolute_result = dao.find_price_change_ranking(
      [2],
      change_ranking_criteria("absolute"),
    )
    up = up_result.items
    down = down_result.items
    absolute = absolute_result.items

    assert [row["complex_id"] for row in up] == [105]
    assert up[0]["change_rate"] == 20
    assert up[0]["start_trade_count"] == 2
    assert up[0]["end_trade_count"] == 2

    assert [row["complex_id"] for row in down] == [106]
    assert down[0]["change_rate"] == -20

    assert [row["complex_id"] for row in absolute] == [105, 106]
    assert [row["rank"] for row in absolute] == [1, 2]
    # 거래부족아파트는 변화폭이 더 커도 최소 거래 건수 미달로 제외된다.
    assert 107 not in [row["complex_id"] for row in absolute]
    assert absolute_result.eligible_count == 2
  finally:
    session.close()


def test_price_change_ranking_applies_area_and_limit():
  """변화율 계산 전 면적 조건을 적용하고 최종 결과 개수를 제한한다."""

  session = make_change_ranking_session()
  try:
    dao = PriceTrendDao(session)
    criteria = change_ranking_criteria("absolute")
    criteria.update({
      "area_min": 99,
      "area_max": 101,
      "limit": 1,
    })

    query_result = dao.find_price_change_ranking([2], criteria)
    rows = query_result.items

    assert len(rows) == 1
    assert rows[0]["rank"] == 1
    assert rows[0]["avg_exclusive_area"] == 100
  finally:
    session.close()


def test_price_change_ranking_uses_raw_rate_before_rounding():
  """아주 작은 상승률도 반올림 전에 상승 대상으로 판정한다."""

  session = make_change_ranking_session()
  try:
    session.add(
      Complex(
        id=108,
        region_id=2,
        parcel_id=1008,
        name="미세상승아파트",
        trade_name="미세상승아파트",
        address="서울 강남구",
      )
    )
    session.add_all([
      Trade(id=2011, complex_id=108, deal_date="2025-01-10", deal_amount=100000, excl_area=100),
      Trade(id=2012, complex_id=108, deal_date="2025-02-10", deal_amount=100000, excl_area=100),
      Trade(id=2013, complex_id=108, deal_date="2025-10-10", deal_amount=100004, excl_area=100),
      Trade(id=2014, complex_id=108, deal_date="2025-11-10", deal_amount=100004, excl_area=100),
    ])
    session.commit()

    result = PriceTrendDao(session).find_price_change_ranking(
      [2],
      change_ranking_criteria("up"),
    )

    # 실제 변화율은 약 0.004%라 반환값은 0.00%지만 상승 대상에는 포함된다.
    micro_change = next(
      row for row in result.items
      if row["complex_id"] == 108
    )
    assert micro_change["change_rate"] == 0
  finally:
    session.close()


# Service

def test_service_handles_complex_trend_from_slots_to_result():
  """단지 슬롯이 Policy·대상 확정·DAO를 거쳐 TrendResult가 된다."""

  session = make_target_session()
  try:
    service = TrendService(
      PriceTrendDao(session),
      base_date="2025-04-30",
    )
    result = service.handle(
      TrendSlots(
        query_type="complex_trend",
        complex_name="래미안대치팰리스",
        period="4m",
        interval="month",
      )
    )

    assert result.success is True
    assert result.reason is None
    assert len(result.data) == 3
    assert isinstance(result.data[0], TrendPoint)
    assert result.criteria["complex_id"] == 101
    assert result.criteria["resolved_complex_name"] == "래미안 대치팰리스"
    assert result.summary["primary_metric"] == "avg_price_per_sqm"
    assert result.summary["total_trade_count"] == 3
  finally:
    session.close()


def test_service_resolves_complex_pyeong_to_actual_area():
  """단지의 단일 평형은 실제 거래 면적을 확정한 뒤 조회한다."""

  session = make_target_session()
  try:
    service = TrendService(
      PriceTrendDao(session),
      base_date="2025-04-30",
    )
    result = service.handle(
      TrendSlots(
        query_type="complex_trend",
        complex_name="래미안대치팰리스",
        pyeong=34,
        period="4m",
        interval="quarter",
      )
    )

    assert result.success is True
    assert result.criteria["selected_exclusive_area"] == 84.8
    assert result.criteria["primary_metric"] == "avg_deal_amount"
    assert len(result.data) == 1
    assert result.data[0].trade_count == 2
  finally:
    session.close()


def test_service_handles_single_and_multiple_region_trends():
  """단일 지역과 복수 지역 모두 region_id 목록으로 조회한다."""

  session = make_target_session()
  try:
    service = TrendService(
      PriceTrendDao(session),
      base_date="2025-01-31",
    )
    single = service.handle(
      TrendSlots(
        query_type="region_trend",
        region_name="대치동",
        period="1m",
      )
    )
    multiple = service.handle(
      TrendSlots(
        query_type="region_trend",
        region_names=["대치동", "강동구"],
        period="1m",
      )
    )

    assert single.success is True
    assert single.criteria["region_ids"] == [3]
    assert single.data[0].trade_count == 2

    assert multiple.success is True
    assert multiple.criteria["region_ids"] == [3, 4]
    assert multiple.data[0].trade_count == 3
  finally:
    session.close()


def test_service_returns_business_failures_in_trend_result():
  """대상 없음과 결과 없음 등을 공통 실패 구조로 반환한다."""

  session = make_target_session()
  try:
    service = TrendService(
      PriceTrendDao(session),
      base_date="2025-04-30",
    )
    target_not_found = service.handle(
      TrendSlots(
        query_type="complex_trend",
        complex_name="없는아파트",
      )
    )
    no_result = service.handle(
      TrendSlots(
        query_type="region_trend",
        region_name="대치동",
        start_date="2024-01-01",
        end_date="2024-12-31",
      )
    )
    insufficient = service.handle(
      TrendSlots(
        query_type="price_change_ranking",
        region_name="대치동",
      )
    )

    assert target_not_found.reason == "target_not_found"
    assert no_result.reason == "no_result"
    assert insufficient.reason == "insufficient_data"
    assert target_not_found.data == []
    assert no_result.data == []
  finally:
    session.close()


def test_service_handles_price_change_ranking():
  """변화율 Policy부터 지역 확정, DAO, DTO 반환까지 전체 흐름을 처리한다."""

  session = make_change_ranking_session()
  try:
    service = TrendService(
      PriceTrendDao(session),
      base_date="2025-12-31",
    )
    result = service.handle(
      TrendSlots(
        query_type="price_change_ranking",
        region_name="강남구",
        period="1y",
        change_direction="absolute",
        limit=2,
      )
    )

    assert result.success is True
    assert all(
      isinstance(item, PriceChangeRankingItem)
      for item in result.data
    )
    assert [item.complex_id for item in result.data] == [105, 106]
    assert result.summary["change_direction"] == "absolute"
    assert result.summary["window_months"] == 3
    assert result.summary["min_trade_count"] == 2
  finally:
    session.close()


def test_service_change_ranking_returns_insufficient_data():
  """두 비교 window의 최소 거래 건수를 충족하지 못하면 실패한다."""

  session = make_change_ranking_session()
  try:
    service = TrendService(
      PriceTrendDao(session),
      base_date="2025-12-31",
    )
    result = service.handle(
      TrendSlots(
        query_type="price_change_ranking",
        region_name="강남구",
        period="1y",
        area=59,
      )
    )

    assert result.success is False
    assert result.reason == "insufficient_data"
    assert result.data == []
  finally:
    session.close()


def test_service_change_ranking_distinguishes_no_direction_result():
  """데이터는 충분하지만 요청 방향 단지가 없으면 no_result를 반환한다."""

  session = make_change_ranking_session()
  try:
    # 상승아파트를 제외하면 선택 지역에는 하락아파트만 남도록 별도 지역을
    # 만들지 않고, 80㎡ 조건으로 하락아파트 거래만 조회되게 데이터를 조정한다.
    session.query(Trade).filter(Trade.complex_id == 106).update({
      Trade.excl_area: 80,
    })
    session.commit()

    service = TrendService(
      PriceTrendDao(session),
      base_date="2025-12-31",
    )
    result = service.handle(
      TrendSlots(
        query_type="price_change_ranking",
        region_name="강남구",
        period="1y",
        area=80,
        change_direction="up",
      )
    )

    assert result.success is False
    assert result.reason == "no_result"
  finally:
    session.close()


def test_service_handles_highest_and_lowest_price_rankings():
  """지역 확정부터 DTO 변환까지 실거래가 순위 전체 흐름을 처리한다."""

  session = make_target_session()
  try:
    service = TrendService(PriceTrendDao(session))

    highest = service.handle(
      TrendSlots(
        query_type="price_ranking",
        region_name="대치동",
        rank_order="highest",
        limit=2,
      )
    )
    lowest = service.handle(
      TrendSlots(
        query_type="price_ranking",
        region_name="대치동",
        rank_order="lowest",
        limit=1,
      )
    )

    assert highest.success is True
    assert [item.complex_id for item in highest.data] == [102, 101]
    assert all(isinstance(item, PriceRankingItem) for item in highest.data)
    assert highest.summary["rank_order"] == "highest"
    assert highest.summary["result_count"] == 2

    assert lowest.success is True
    assert len(lowest.data) == 1
    assert lowest.data[0].complex_id == 101
    assert lowest.data[0].deal_amount == 200000
  finally:
    session.close()


def test_service_price_ranking_returns_no_result_for_empty_conditions():
  """해당 기간에 거래가 없으면 성공 빈 목록이 아니라 no_result를 반환한다."""

  session = make_target_session()
  try:
    service = TrendService(
      PriceTrendDao(session),
      base_date="2024-12-31",
    )
    result = service.handle(
      TrendSlots(
        query_type="price_ranking",
        region_name="대치동",
        period="1y",
      )
    )

    assert result.success is False
    assert result.reason == "no_result"
    assert result.data == []
  finally:
    session.close()


def test_service_reads_max_deal_date_when_base_date_is_not_injected():
  """고정 기준일이 없으면 기본 기간 계산 시 DB 최신일을 한 번 조회한다."""

  session = make_target_session()
  try:
    service = TrendService(PriceTrendDao(session))
    result = service.handle(
      TrendSlots(
        query_type="complex_trend",
        complex_name="래미안대치팰리스",
      )
    )

    assert result.success is True
    assert result.criteria["base_date"] == "2025-04-10"
    assert result.criteria["period"] == "3y"
  finally:
    session.close()
