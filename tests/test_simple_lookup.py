from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.chatbot.features.simple_lookup.dao import SimpleLookupDao
from app.chatbot.features.simple_lookup.dto import (
    QUERY_COMPLEX_PRICE_RECORD,
    QUERY_LOCATION,
    QUERY_REGION_PRICE_RANKING,
    QUERY_TRADE_HISTORY,
    SimpleLookupCriteria,
    SimpleLookupSlots,
)
from app.chatbot.features.simple_lookup.policy import SimpleLookupPolicy
from app.chatbot.features.simple_lookup.service import SimpleLookupService, run_simple_lookup
from app.chatbot.features.simple_lookup.slots import extract_simple_lookup_slots
from app.database import SessionLocal, ensure_initialized
from app.models import Complex, Region, Trade


POSTGRES_TEST_DATABASE_URL = (
    "postgresql+psycopg://home_search:home_search@127.0.0.1:55432/home_search"
)

REGION_ID = 990001
ALPHA_ID = 990101
BETA_ID = 990102
CASE_APT_A_ID = 990201
CASE_APT_B_ID = 990202


@pytest.fixture()
def pg_session() -> Session:
    engine = create_engine(POSTGRES_TEST_DATABASE_URL)
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(text("SELECT 1"))
        session = Session(bind=connection)
        seed_h1_data(session)
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()
    engine.dispose()


def seed_h1_data(session: Session) -> None:
    session.add(
        Region(
            id=REGION_ID,
            code="H1-TEST-DISTRICT",
            name="H1District",
            type="district",
            center_lat=37.5,
            center_lng=127.0,
        )
    )
    session.add_all(
        [
            Complex(
                id=ALPHA_ID,
                region_id=REGION_ID,
                parcel_id=9901001,
                name="H1 Alpha Tower",
                trade_name="H1Alpha",
                address="Seoul H1 Alpha",
                latitude=37.5,
                longitude=127.1,
            ),
            Complex(
                id=BETA_ID,
                region_id=REGION_ID,
                parcel_id=9901002,
                name="H1 Beta Tower",
                trade_name="H1Beta",
                address="Seoul H1 Beta",
                latitude=37.6,
                longitude=127.2,
            ),
            Complex(
                id=CASE_APT_A_ID,
                region_id=REGION_ID,
                parcel_id=9902001,
                name="테스트해동아파트A동(134-5)",
                trade_name="테스트해동아파트A동(134-5)",
                address="테스트동 134-5",
                latitude=37.51064,
                longitude=127.1197312,
            ),
            Complex(
                id=CASE_APT_B_ID,
                region_id=REGION_ID,
                parcel_id=9902002,
                name="테스트해동아파트B동(134-22)",
                trade_name="테스트해동아파트B동(134-22)",
                address="테스트동 134-22",
                latitude=37.5105058,
                longitude=127.1196477,
            ),
        ]
    )
    session.add_all(
        [
            Trade(
                id=99010001,
                complex_id=ALPHA_ID,
                deal_date="2010-01-10",
                deal_amount=100000,
                excl_area=84.8,
                floor=4,
            ),
            Trade(
                id=99010002,
                complex_id=ALPHA_ID,
                deal_date="2012-06-10",
                deal_amount=120000,
                excl_area=84.8,
                floor=8,
            ),
            Trade(
                id=99010003,
                complex_id=ALPHA_ID,
                deal_date="2015-01-10",
                deal_amount=130000,
                excl_area=84.8,
                floor=10,
            ),
            Trade(
                id=99010004,
                complex_id=ALPHA_ID,
                deal_date="2026-03-01",
                deal_amount=210000,
                excl_area=84.8,
                floor=12,
            ),
            Trade(
                id=99010005,
                complex_id=ALPHA_ID,
                deal_date="2026-05-01",
                deal_amount=190000,
                excl_area=59.9,
                floor=6,
            ),
            Trade(
                id=99010006,
                complex_id=BETA_ID,
                deal_date="2026-04-01",
                deal_amount=220000,
                excl_area=84.0,
                floor=20,
            ),
        ]
    )
    session.flush()


def test_h1_location_uses_postgresql(pg_session: Session):
    dialect = pg_session.get_bind().dialect.name
    service = SimpleLookupService(SimpleLookupDao(pg_session))

    result = service.handle(
        SimpleLookupSlots(query_type=QUERY_LOCATION, target_name="H1Alpha")
    )

    assert dialect == "postgresql"
    assert result.success is True
    assert result.data[0].complex_id == ALPHA_ID
    assert result.data[0].address == "Seoul H1 Alpha"


def test_location_matches_case_insensitive_building_suffix(pg_session: Session):
    service = SimpleLookupService(SimpleLookupDao(pg_session))

    result = service.handle(
        SimpleLookupSlots(query_type=QUERY_LOCATION, target_name="테스트해동아파트b동")
    )

    assert result.success is True
    assert result.data[0].complex_id == CASE_APT_B_ID
    assert result.data[0].address == "테스트동 134-22"


def test_location_keeps_ambiguous_base_name_for_building_variants(pg_session: Session):
    service = SimpleLookupService(SimpleLookupDao(pg_session))

    result = service.handle(
        SimpleLookupSlots(query_type=QUERY_LOCATION, target_name="테스트해동아파트")
    )

    assert result.success is False
    assert result.reason == "ambiguous_target"
    candidate_ids = {candidate["complex_id"] for candidate in result.candidates}
    assert CASE_APT_A_ID in candidate_ids
    assert CASE_APT_B_ID in candidate_ids


def test_h1_trade_history_period_filter_and_latest_oldest(pg_session: Session):
    dao = SimpleLookupDao(pg_session)

    latest_criteria = SimpleLookupPolicy().build_criteria(
        SimpleLookupSlots(
            query_type=QUERY_TRADE_HISTORY,
            target_name="H1Alpha",
            start_date=date(2010, 1, 1),
            end_date=date(2014, 12, 31),
        )
    )
    _, latest_trades = dao.find_trade_history(latest_criteria)

    oldest_criteria = latest_criteria.model_copy(update={"sort_order": "oldest"})
    _, oldest_trades = dao.find_trade_history(oldest_criteria)

    assert [trade.deal_date for trade in latest_trades] == [
        "2012-06-10",
        "2010-01-10",
    ]
    assert [trade.deal_date for trade in oldest_trades] == [
        "2010-01-10",
        "2012-06-10",
    ]


def test_h1_complex_price_record_highest_and_lowest(pg_session: Session):
    service = SimpleLookupService(SimpleLookupDao(pg_session))

    highest = service.handle(
        SimpleLookupSlots(
            query_type=QUERY_COMPLEX_PRICE_RECORD,
            target_name="H1Alpha",
            price_order="highest",
        )
    )
    lowest = service.handle(
        SimpleLookupSlots(
            query_type=QUERY_COMPLEX_PRICE_RECORD,
            target_name="H1Alpha",
            price_order="lowest",
        )
    )

    assert highest.success is True
    assert highest.data[0].deal_amount == 210000
    assert lowest.success is True
    assert lowest.data[0].deal_amount == 100000


def test_h1_region_price_ranking_highest_and_lowest(pg_session: Session):
    service = SimpleLookupService(SimpleLookupDao(pg_session))

    highest = service.handle(
        SimpleLookupSlots(
            query_type=QUERY_REGION_PRICE_RANKING,
            target_name="H1District",
            price_order="highest",
            limit=2,
        )
    )
    lowest = service.handle(
        SimpleLookupSlots(
            query_type=QUERY_REGION_PRICE_RANKING,
            target_name="H1District",
            price_order="lowest",
            limit=2,
        )
    )

    assert highest.success is True
    assert [row.deal_amount for row in highest.data] == [220000, 210000]
    assert lowest.success is True
    assert [row.deal_amount for row in lowest.data] == [100000, 120000]


def test_h1_year_duration_slot_maps_to_explicit_date_range():
    slots = extract_simple_lookup_slots("H1Alpha 2010년부터 5년간 최고가")

    assert slots["start_date"] == "2010-01-01"
    assert slots["end_date"] == "2014-12-31"


def test_run_simple_lookup_returns_same_result_shape_for_validation_errors():
    result = run_simple_lookup(
        object(),
        {"query_type": QUERY_LOCATION},
    )

    assert result["handler"] == "simple_lookup"
    assert result["success"] is False
    assert result["query_type"] == QUERY_LOCATION
    assert result["reason"] == "invalid_request"
    assert result["criteria"] == {}
    assert result["candidates"] == []
    assert set(result) == {
        "handler",
        "success",
        "query_type",
        "criteria",
        "reason",
        "message",
        "candidates",
    }


def test_h1_recent_period_number_is_not_used_as_limit():
    slots = extract_simple_lookup_slots("H1Alpha 최근 6개월 최고가")

    assert slots["period"] == "6m"
    assert "limit" not in slots


def test_extract_simple_lookup_slots_uses_recent_count_as_limit():
    slots = extract_simple_lookup_slots("래미안대치팰리스 최근 5건 보여줘")

    assert slots["query_type"] == QUERY_TRADE_HISTORY
    assert slots["limit"] == 5


def test_run_simple_lookup_period_filter_works_on_sqlite_fixture():
    ensure_initialized()

    with SessionLocal() as session:
        result = run_simple_lookup(
            session,
            {
                "query_type": QUERY_TRADE_HISTORY,
                "target_name": "래미안대치팰리스",
                "period": "1y",
            },
            "래미안대치팰리스 최근 1년 거래 내역 보여줘",
        )

    assert result["handler"] == "simple_lookup"
    assert result["success"] is True
    assert result["criteria"]["target_name"] == "래미안대치팰리스"
    assert result["data"]
