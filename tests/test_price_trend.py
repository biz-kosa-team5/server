from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.chatbot.features.price_trend import (
    ANALYSIS_RANKING,
    ANALYSIS_TIMESERIES,
    TARGET_COMPLEX,
    TARGET_REGION,
    TrendError,
    TrendSlots,
    extract_price_trend_slots,
    normalize_trend_policy,
    run_price_trend,
)
from app.models import Base, Complex, Region, Trade


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)

    session.add_all([
        Region(id=1, code="SEOUL", name="서울특별시", type="city", center_lat=37.56, center_lng=126.97),
        Region(id=2, code="GANGNAM", name="강남구", type="district", parent_id=1, center_lat=37.51, center_lng=127.04),
        Region(id=3, code="SEOCHO", name="서초구", type="district", parent_id=1, center_lat=37.48, center_lng=127.03),
        Region(id=4, code="SONGPA", name="송파구", type="district", parent_id=1, center_lat=37.50, center_lng=127.11),
        Complex(id=10, region_id=2, parcel_id=10, name="래미안대치팰리스", address="대치동"),
        Complex(id=20, region_id=2, parcel_id=20, name="은마", address="대치동"),
        Complex(id=30, region_id=3, parcel_id=30, name="서초더샵", address="서초동"),
        Complex(id=40, region_id=4, parcel_id=40, name="잠실엘스", address="잠실동"),
    ])
    session.add_all([
        Trade(id=1, complex_id=10, deal_date="2025-07-10", deal_amount=100000, excl_area=84),
        Trade(id=2, complex_id=10, deal_date="2025-08-10", deal_amount=102000, excl_area=84),
        Trade(id=3, complex_id=10, deal_date="2026-04-10", deal_amount=120000, excl_area=84),
        Trade(id=4, complex_id=10, deal_date="2026-05-10", deal_amount=122000, excl_area=84),
        Trade(id=5, complex_id=20, deal_date="2025-07-15", deal_amount=90000, excl_area=84),
        Trade(id=6, complex_id=20, deal_date="2025-08-15", deal_amount=92000, excl_area=84),
        Trade(id=7, complex_id=20, deal_date="2026-04-15", deal_amount=85000, excl_area=84),
        Trade(id=8, complex_id=20, deal_date="2026-05-15", deal_amount=84000, excl_area=84),
        Trade(id=9, complex_id=30, deal_date="2025-07-20", deal_amount=110000, excl_area=84),
        Trade(id=10, complex_id=30, deal_date="2025-08-20", deal_amount=111000, excl_area=84),
        Trade(id=11, complex_id=30, deal_date="2026-04-20", deal_amount=100000, excl_area=84),
        Trade(id=12, complex_id=30, deal_date="2026-05-20", deal_amount=99000, excl_area=84),
        Trade(id=13, complex_id=40, deal_date="2025-07-25", deal_amount=80000, excl_area=84),
        Trade(id=14, complex_id=40, deal_date="2026-05-25", deal_amount=130000, excl_area=84),
    ])
    session.commit()
    try:
        yield session
    finally:
        session.close()


def slots(**overrides) -> dict:
    values = {
        "analysis_type": ANALYSIS_TIMESERIES,
        "target_type": TARGET_REGION,
        "target_name": "강남구",
    }
    values.update(overrides)
    return values


def test_slots_accept_single_target_name():
    item = TrendSlots(
        analysis_type=ANALYSIS_TIMESERIES,
        target_type=TARGET_COMPLEX,
        target_name="은마아파트",
    )

    assert item.target_name == "은마아파트"


def test_policy_keeps_only_minimum_rules():
    spec = normalize_trend_policy(
        TrendSlots(**slots(target_type=TARGET_COMPLEX, target_name="은마아파트", pyeong=34, period="1y")),
        base_date=date(2025, 12, 31),
    )

    assert spec.target_name == "은마아파트"
    assert spec.interval == "month"
    assert spec.start_date == "2024-12-31"
    assert spec.end_date == "2025-12-31"
    assert spec.area_min == pytest.approx(81.3)
    assert spec.area_max == pytest.approx(87.3)


@pytest.mark.parametrize(
    "bad_slots",
    [
        slots(interval="week"),
        slots(area=84, pyeong=34),
        slots(analysis_type=ANALYSIS_RANKING, target_type=TARGET_COMPLEX, target_name="은마"),
        slots(analysis_type=ANALYSIS_RANKING, rank_by="unknown"),
    ],
)
def test_policy_rejects_bad_inputs(bad_slots):
    with pytest.raises(TrendError):
        normalize_trend_policy(TrendSlots(**bad_slots), base_date="2025-12-31")


def test_period_extractor_keeps_relative_period():
    assert extract_price_trend_slots("은마아파트 최근 1년 시세 흐름")["period"] == "1y"
    assert extract_price_trend_slots("강남구 최근 6개월 시세추이")["period"] == "6m"


def test_complex_timeseries(session: Session):
    result = run_price_trend(
        session,
        slots(target_type=TARGET_COMPLEX, target_name="은마", period="1y"),
        "은마아파트 시세추이 알려줘",
    )

    assert result["success"] is True
    assert result["criteria"]["target_name"] == "은마"
    assert result["criteria"]["interval"] == "month"
    assert sum(row["trade_count"] for row in result["results"]) == 4


def test_complex_timeseries_with_pyeong(session: Session):
    result = run_price_trend(
        session,
        slots(target_type=TARGET_COMPLEX, target_name="은마", pyeong=34, period="1y"),
        "은마아파트 34평 시세추이 알려줘",
    )

    assert result["success"] is True
    assert result["criteria"]["area_min"] == pytest.approx(81.3)
    assert result["criteria"]["area_max"] == pytest.approx(87.3)


def test_region_timeseries(session: Session):
    result = run_price_trend(session, slots(target_name="강남구", period="1y"), "강남구 시세추이")

    assert result["success"] is True
    assert result["criteria"]["target_name"] == "강남구"
    assert sum(row["trade_count"] for row in result["results"]) == 8


def test_gangnam_3_timeseries(session: Session):
    result = run_price_trend(session, slots(target_name="강남3구", period="1y"), "강남 3구 시세추이")

    assert result["success"] is True
    assert result["criteria"]["target_name"] == "강남3구"
    assert sum(row["trade_count"] for row in result["results"]) == 14


def test_change_rate_ranking_up_and_down(session: Session):
    up = run_price_trend(
        session,
        slots(analysis_type=ANALYSIS_RANKING, target_name="강남구", rank_by="change_rate", direction="desc", limit=5),
        "최근 1년 강남구에서 많이 오른 아파트 TOP 5 알려줘",
    )
    down = run_price_trend(
        session,
        slots(analysis_type=ANALYSIS_RANKING, target_name="서초구", rank_by="change_rate", direction="asc", limit=5),
        "최근 1년 서초구에서 많이 내린 아파트 5곳 보여줘",
    )

    assert up["success"] is True
    assert up["results"][0]["complex_name"] == "래미안대치팰리스"
    assert down["success"] is True
    assert down["results"][0]["complex_name"] == "서초더샵"


def test_price_rankings(session: Session):
    highest = run_price_trend(
        session,
        slots(analysis_type=ANALYSIS_RANKING, target_name="강남구", rank_by="max_deal_amount", direction="desc", limit=5),
        "강남구 최고가 아파트 TOP 5 알려줘",
    )
    lowest = run_price_trend(
        session,
        slots(analysis_type=ANALYSIS_RANKING, target_name="송파구", rank_by="min_deal_amount", direction="asc", limit=5),
        "송파구 최저가 아파트 5곳 알려줘",
    )

    assert highest["success"] is True
    assert highest["results"][0]["max_deal_amount"] == 122000
    assert lowest["success"] is True
    assert lowest["results"][0]["complex_name"] == "잠실엘스"
    assert lowest["results"][0]["min_deal_amount"] == 80000


def test_validation_error_response(session: Session):
    result = run_price_trend(session, {"analysis_type": "unknown", "target_type": "region", "target_name": "강남구"})

    assert result["handler"] == "price_trend"
    assert result["success"] is False
    assert result["reason"] == "invalid_request"
