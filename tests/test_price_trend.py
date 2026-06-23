"""시세추이 DTO·Policy·DAO·Service 테스트."""

import json
from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.chatbot.features.price_trend import (
    QUERY_COMPLEX_TREND,
    QUERY_PRICE_CHANGE_RANKING,
    QUERY_REGION_TREND,
    PriceTrendDao,
    TrendError,
    TrendService,
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
        Region(
            id=1,
            code="SEOUL",
            name="서울특별시",
            type="city",
            center_lat=37.56,
            center_lng=126.97,
        ),
        Region(
            id=2,
            code="GANGNAM",
            name="강남구",
            type="district",
            parent_id=1,
            center_lat=37.51,
            center_lng=127.04,
        ),
        Region(
            id=3,
            code="SEOCHO",
            name="서초구",
            type="district",
            parent_id=1,
            center_lat=37.48,
            center_lng=127.03,
        ),
        Complex(
            id=10,
            region_id=2,
            parcel_id=10,
            name="래미안대치팰리스",
            trade_name="래미안 대치 팰리스",
            address="서울 강남구",
        ),
        Complex(
            id=20,
            region_id=2,
            parcel_id=20,
            name="은마아파트",
            address="서울 강남구",
        ),
        Complex(
            id=30,
            region_id=3,
            parcel_id=30,
            name="서초테스트",
            address="서울 서초구",
        ),
    ])
    session.add_all([
        Trade(id=1, complex_id=10, deal_date="2025-01-10", deal_amount=100000, excl_area=84),
        Trade(id=2, complex_id=10, deal_date="2025-02-10", deal_amount=102000, excl_area=84),
        Trade(id=3, complex_id=10, deal_date="2025-11-10", deal_amount=120000, excl_area=84),
        Trade(id=4, complex_id=10, deal_date="2025-12-10", deal_amount=122000, excl_area=84),
        Trade(id=5, complex_id=20, deal_date="2025-01-15", deal_amount=90000, excl_area=84),
        Trade(id=6, complex_id=20, deal_date="2025-02-15", deal_amount=92000, excl_area=84),
        Trade(id=7, complex_id=20, deal_date="2025-11-15", deal_amount=85000, excl_area=84),
        Trade(id=8, complex_id=20, deal_date="2025-12-15", deal_amount=84000, excl_area=84),
        Trade(id=9, complex_id=30, deal_date="2025-12-20", deal_amount=130000, excl_area=84),
    ])
    session.commit()
    try:
        yield session
    finally:
        session.close()


def test_slots_accept_only_three_query_types():
    for query_type in (
        QUERY_COMPLEX_TREND,
        QUERY_REGION_TREND,
        QUERY_PRICE_CHANGE_RANKING,
    ):
        assert TrendSlots(query_type=query_type).query_type == query_type

    with pytest.raises(ValidationError):
        TrendSlots(query_type="price_ranking")


def test_slots_reject_unknown_and_boolean_values():
    with pytest.raises(ValidationError):
        TrendSlots(query_type=QUERY_REGION_TREND, unknown="value")
    with pytest.raises(ValidationError):
        TrendSlots(query_type=QUERY_REGION_TREND, area=True)


def test_policy_normalizes_target_period_area_and_interval():
    criteria = normalize_trend_policy(
        TrendSlots(
            query_type=QUERY_COMPLEX_TREND,
            complex_name="  래미안  대치팰리스 ",
            area=84,
            period="1y",
        ),
        base_date=date(2025, 12, 31),
    )

    assert criteria.complex_name == "래미안 대치팰리스"
    assert criteria.area_min == 83
    assert criteria.area_max == 85
    assert criteria.start_date == "2024-12-31"
    assert criteria.end_date == "2025-12-31"
    assert criteria.interval == "month"


def test_policy_converts_pyeong_and_deduplicates_regions():
    criteria = normalize_trend_policy(
        TrendSlots(
            query_type=QUERY_REGION_TREND,
            region_names=[" 강남구 ", "서초구", "강남구"],
            pyeong=34,
        ),
        base_date="2025-12-31",
    )

    assert criteria.region_names == ("강남구", "서초구")
    assert criteria.area_min == pytest.approx(81.3)
    assert criteria.area_max == pytest.approx(87.3)


@pytest.mark.parametrize(
    ("slots", "reason"),
    [
        (
            TrendSlots(query_type=QUERY_COMPLEX_TREND),
            "missing_area",
        ),
        (
            TrendSlots(query_type=QUERY_REGION_TREND),
            "invalid_request",
        ),
        (
            TrendSlots(
                query_type=QUERY_COMPLEX_TREND,
                complex_name="래미안",
                region_name="강남구",
            ),
            "invalid_request",
        ),
        (
            TrendSlots(
                query_type=QUERY_REGION_TREND,
                region_name="강남구",
                interval="week",
            ),
            "invalid_request",
        ),
        (
            TrendSlots(
                query_type=QUERY_PRICE_CHANGE_RANKING,
                region_name="강남구",
                period="1y",
                start_date="2025-01-01",
            ),
            "invalid_request",
        ),
    ],
)
def test_policy_rejects_invalid_combinations(slots: TrendSlots, reason: str):
    with pytest.raises(TrendError) as captured:
        normalize_trend_policy(slots, base_date="2025-12-31")
    assert captured.value.reason == reason


def test_policy_builds_price_change_windows():
    criteria = normalize_trend_policy(
        TrendSlots(
            query_type=QUERY_PRICE_CHANGE_RANKING,
            region_name="강남구",
            period="1y",
            change_direction="down",
            limit=3,
        ),
        base_date="2025-12-31",
    )

    assert criteria.region_names == ("강남구",)
    assert criteria.change_direction == "down"
    assert criteria.limit == 3
    assert criteria.start_window_start == "2024-12-31"
    assert criteria.start_window_end == "2025-03-30"
    assert criteria.end_window_start == "2025-10-01"
    assert criteria.end_window_end == "2025-12-31"


def test_slot_extractor_routes_supported_questions():
    complex_slots = extract_price_trend_slots("은마아파트 84㎡ 최근 1년 시세 추이")
    assert complex_slots["query_type"] == QUERY_COMPLEX_TREND
    assert complex_slots["complex_name"] == "은마아파트"
    assert complex_slots["area"] == 84
    assert extract_price_trend_slots("강남구 최근 1년 시세 추이")["query_type"] == QUERY_REGION_TREND
    ranking = extract_price_trend_slots("강남구 최근 1년 많이 오른 아파트 5곳")
    assert ranking["query_type"] == QUERY_PRICE_CHANGE_RANKING
    assert ranking["limit"] == 5


def test_dao_complex_and_region_trend(session: Session):
    dao = PriceTrendDao(session)
    complex_criteria = normalize_trend_policy(
        TrendSlots(
            query_type=QUERY_COMPLEX_TREND,
            complex_name="래미안대치팰리스",
            area=84,
            period="1y",
        ),
        base_date="2025-12-31",
    )
    region_criteria = normalize_trend_policy(
        TrendSlots(
            query_type=QUERY_REGION_TREND,
            region_name="강남구",
            period="1y",
        ),
        base_date="2025-12-31",
    )

    complex_rows = dao.find_complex_trend(complex_criteria)
    region_rows = dao.find_region_trend(region_criteria)

    assert sum(row["trade_count"] for row in complex_rows) == 4
    assert sum(row["trade_count"] for row in region_rows) == 8


def test_dao_price_change_ranking(session: Session):
    criteria = normalize_trend_policy(
        TrendSlots(
            query_type=QUERY_PRICE_CHANGE_RANKING,
            region_name="강남구",
            period="1y",
        ),
        base_date="2025-12-31",
    )

    rows = PriceTrendDao(session).find_price_change_ranking(criteria)

    assert [row["complex_name"] for row in rows] == ["래미안대치팰리스"]
    assert rows[0]["change_rate"] > 0


def test_service_returns_success_and_business_failure(session: Session):
    service = TrendService(PriceTrendDao(session))
    success = service.handle(
        TrendSlots(
            query_type=QUERY_COMPLEX_TREND,
            complex_name="래미안대치팰리스",
            area=84,
            period="1y",
        )
    )
    failure = service.handle(
        TrendSlots(
            query_type=QUERY_COMPLEX_TREND,
            complex_name="없는아파트",
            area=84,
            period="1y",
        )
    )

    assert success.success is True
    assert success.summary["observed_period_count"] == 2
    assert failure.success is False
    assert failure.reason == "target_not_found"


def test_run_price_trend_keeps_external_response_contract(session: Session):
    result = run_price_trend(
        session,
        {
            "query_type": QUERY_REGION_TREND,
            "region_name": "강남구",
            "period": "1y",
        },
        "강남구 최근 1년 시세 추이",
    )

    assert result["handler"] == "price_trend"
    assert result["success"] is True
    assert result["query_type"] == QUERY_REGION_TREND


def test_run_price_trend_reports_validation_errors(session: Session):
    result = run_price_trend(
        session,
        {"query_type": "price_ranking"},
    )

    assert result["handler"] == "price_trend"
    assert result["success"] is False
    assert result["reason"] == "invalid_request"
    assert result["errors"]


def test_console_output_for_price_trend(session: Session):
    """`pytest -s` 실행 시 외부 응답 구조를 콘솔에서 확인한다."""

    success = run_price_trend(
        session,
        {
            "query_type": QUERY_COMPLEX_TREND,
            "complex_name": "래미안대치팰리스",
            "area": 84,
            "period": "1y",
        },
        "래미안대치팰리스 최근 1년 시세 추이",
    )
    failure = run_price_trend(
        session,
        {"query_type": "price_ranking"},
        "강남구에서 가장 비싼 아파트",
    )

    print("\n[시세추이 성공 응답]")
    print(json.dumps(success, ensure_ascii=False, indent=2))
    print("\n[시세추이 실패 응답]")
    print(json.dumps(failure, ensure_ascii=False, indent=2))

    assert success["handler"] == "price_trend"
    assert success["success"] is True
    assert failure["handler"] == "price_trend"
    assert failure["reason"] == "invalid_request"
