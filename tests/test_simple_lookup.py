"""단순조회 DTO·Policy·DAO·Service 테스트."""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.chatbot.features.simple_lookup.dao import SimpleLookupDao
from app.chatbot.features.simple_lookup.dto import (
    QUERY_LOCATION,
    QUERY_TRADE,
    SimpleLookupCriteria,
    SimpleLookupError,
    SimpleLookupResult,
    SimpleLookupSlots,
)
from app.chatbot.features.simple_lookup.policy import (
    BASE_DATE,
    normalize_simple_lookup_policy,
)
from app.chatbot.features.simple_lookup.service import (
    SimpleLookupService,
    run_simple_lookup,
)
from app.models import Base, Complex, Region, Trade


def make_session() -> Session:
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
            name="은마",
            trade_name="은마",
            address="서울 강남구 대치동",
            latitude=37.497524,
            longitude=127.065451,
        ),
        Complex(
            id=106,
            region_id=1,
            parcel_id=1006,
            name="스카이써밋아파트",
            trade_name="스카이써밋아파트",
            address="서울 강남구 대치동",
            latitude=37.501141,
            longitude=127.058316,
        ),
        Complex(
            id=107,
            region_id=1,
            parcel_id=1007,
            name="개포주공5단지",
            trade_name="개포주공5단지",
            address="서울 강남구 개포동",
            latitude=37.489,
            longitude=127.068,
        ),
    ])
    session.add_all([
        Trade(
            id=1,
            complex_id=101,
            deal_date="2025-01-10",
            deal_amount=200000,
            excl_area=84.8,
            floor=10,
        ),
        Trade(
            id=2,
            complex_id=101,
            deal_date="2025-02-10",
            deal_amount=210000,
            excl_area=84.8,
            floor=12,
        ),
        Trade(
            id=3,
            complex_id=101,
            deal_date="2025-03-10",
            deal_amount=190000,
            excl_area=59.9,
            floor=8,
        ),
    ])
    session.commit()
    return session


def assert_lookup_error(reason: str, callback) -> SimpleLookupError:
    with pytest.raises(SimpleLookupError) as captured:
        callback()
    assert captured.value.reason == reason
    return captured.value


def test_result_has_one_stable_shape():
    criteria = SimpleLookupCriteria(
        query_type=QUERY_LOCATION,
        complex_name="잠실엘스",
    )

    success = SimpleLookupResult.ok(
        query_type=QUERY_LOCATION,
        criteria=criteria,
        data=[{"complex_name": "잠실엘스"}],
        message="조회했습니다.",
    ).model_dump(mode="json")
    failure = SimpleLookupResult.fail(
        query_type=QUERY_LOCATION,
        reason="no_result",
        message="결과가 없습니다.",
    ).model_dump(mode="json")

    expected_keys = {
        "handler",
        "success",
        "query_type",
        "criteria",
        "data",
        "reason",
        "message",
        "candidates",
    }
    assert set(success) == expected_keys
    assert set(failure) == expected_keys


def test_policy_normalizes_area_pyeong_and_limit():
    area = normalize_simple_lookup_policy(
        SimpleLookupSlots(
            query_type=QUERY_TRADE,
            complex_name="  잠실엘스  ",
            area=84,
            limit=100,
        )
    )
    pyeong = normalize_simple_lookup_policy(
        SimpleLookupSlots(
            query_type=QUERY_TRADE,
            complex_name="잠실엘스",
            pyeong=34,
        )
    )

    assert area.complex_name == "잠실엘스"
    assert area.area_min == 83
    assert area.area_max == 85
    assert area.limit == 20
    assert pyeong.area_min == 81.15
    assert pyeong.area_max == 87.15
    assert pyeong.limit == 5


def test_policy_removes_spaces_from_complex_name():
    criteria = normalize_simple_lookup_policy(
        SimpleLookupSlots(
            query_type=QUERY_LOCATION,
            complex_name="개포 5단지",
        )
    )

    assert criteria.complex_name == "개포5단지"


def test_policy_treats_square_meter_text_as_area_when_llm_uses_pyeong():
    criteria = normalize_simple_lookup_policy(
        SimpleLookupSlots(
            query_type=QUERY_TRADE,
            complex_name="잠실엘스",
            pyeong=84,
            original_question="잠실엘스 84㎡ 최근 거래내역 알려줘",
        )
    )

    assert criteria.area_min == 83
    assert criteria.area_max == 85


def test_policy_rejects_new_record_price_questions():
    error = assert_lookup_error(
        "unsupported_query",
        lambda: normalize_simple_lookup_policy(
            SimpleLookupSlots(
                query_type=QUERY_TRADE,
                complex_name="은마아파트",
                original_question="은마아파트 신고가 갱신했어?",
            )
        ),
    )

    assert "신고가" in error.message


def test_policy_normalizes_trade_sort_order():
    default_order = normalize_simple_lookup_policy(
        SimpleLookupSlots(
            query_type=QUERY_TRADE,
            complex_name="잠실엘스",
        )
    )
    oldest_order = normalize_simple_lookup_policy(
        SimpleLookupSlots(
            query_type=QUERY_TRADE,
            complex_name="잠실엘스",
            sort_order="oldest",
        )
    )

    assert default_order.sort_order == "latest"
    assert oldest_order.sort_order == "oldest"


def test_policy_normalizes_price_order_only_when_provided():
    default_order = normalize_simple_lookup_policy(
        SimpleLookupSlots(
            query_type=QUERY_TRADE,
            complex_name="잠실엘스",
        )
    )
    lowest_order = normalize_simple_lookup_policy(
        SimpleLookupSlots(
            query_type=QUERY_TRADE,
            complex_name="잠실엘스",
            price_order="lowest",
        )
    )

    assert default_order.price_order is None
    assert default_order.limit == 5
    assert lowest_order.price_order == "lowest"
    assert lowest_order.limit == 1


def test_policy_rejects_invalid_request_values():
    invalid_slots = [
        SimpleLookupSlots(
            query_type="unknown",
            complex_name="잠실엘스",
        ),
        SimpleLookupSlots(
            query_type=QUERY_TRADE,
            complex_name="잠실엘스",
            area=84,
            pyeong=34,
        ),
        SimpleLookupSlots(
            query_type=QUERY_TRADE,
            complex_name="잠실엘스",
            limit=0,
        ),
        SimpleLookupSlots(
            query_type=QUERY_TRADE,
            complex_name="잠실엘스",
            price_order="invalid",
        ),
    ]

    for slots in invalid_slots:
        assert_lookup_error(
            "invalid_request",
            lambda slots=slots: normalize_simple_lookup_policy(slots),
        )


def test_policy_normalizes_supported_period_combinations():
    period = normalize_simple_lookup_policy(
        SimpleLookupSlots(
            query_type=QUERY_TRADE,
            complex_name="잠실엘스",
            period="1y",
        )
    )
    explicit = normalize_simple_lookup_policy(
        SimpleLookupSlots(
            query_type=QUERY_TRADE,
            complex_name="잠실엘스",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        )
    )
    start_only = normalize_simple_lookup_policy(
        SimpleLookupSlots(
            query_type=QUERY_TRADE,
            complex_name="잠실엘스",
            start_date=date(2025, 1, 1),
        )
    )
    end_only = normalize_simple_lookup_policy(
        SimpleLookupSlots(
            query_type=QUERY_TRADE,
            complex_name="잠실엘스",
            end_date=date(2025, 12, 31),
        )
    )
    from_start = normalize_simple_lookup_policy(
        SimpleLookupSlots(
            query_type=QUERY_TRADE,
            complex_name="잠실엘스",
            start_date=date(2023, 1, 31),
            period="1m",
        )
    )

    assert (period.start_date, period.end_date) == (
        date(2025, 6, 20),
        BASE_DATE,
    )
    assert (explicit.start_date, explicit.end_date) == (
        date(2025, 1, 1),
        date(2025, 12, 31),
    )
    assert (start_only.start_date, start_only.end_date) == (
        date(2025, 1, 1),
        BASE_DATE,
    )
    assert (end_only.start_date, end_only.end_date) == (
        None,
        date(2025, 12, 31),
    )
    assert (from_start.start_date, from_start.end_date) == (
        date(2023, 1, 31),
        date(2023, 2, 28),
    )


def test_policy_rejects_unsupported_period_combinations():
    invalid_slots = [
        SimpleLookupSlots(
            query_type=QUERY_TRADE,
            complex_name="잠실엘스",
            period="1y",
            end_date=date(2025, 12, 31),
        ),
        SimpleLookupSlots(
            query_type=QUERY_TRADE,
            complex_name="잠실엘스",
            period="1y",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        ),
        SimpleLookupSlots(
            query_type=QUERY_TRADE,
            complex_name="잠실엘스",
            start_date=date(2025, 12, 31),
            end_date=date(2025, 1, 1),
        ),
    ]

    for slots in invalid_slots:
        assert_lookup_error(
            "invalid_request",
            lambda slots=slots: normalize_simple_lookup_policy(slots),
        )


def test_dao_public_methods_receive_only_criteria():
    with make_session() as session:
        dao = SimpleLookupDao(session)
        criteria = SimpleLookupCriteria(
            query_type=QUERY_TRADE,
            complex_name="잠실엘스",
            area_min=83,
            area_max=85,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            limit=1,
        )

        rows = dao.find_trade_history(criteria)

        assert rows == [{
            "complex_id": 101,
            "complex_name": "잠실엘스",
            "trade_name": "잠실엘스",
            "deal_date": "2025-02-10",
            "deal_amount": 210000,
            "exclusive_area": 84.8,
            "floor": 12,
            "apt_dong": None,
        }]


def test_dao_can_return_oldest_trade_history():
    with make_session() as session:
        dao = SimpleLookupDao(session)
        criteria = SimpleLookupCriteria(
            query_type=QUERY_TRADE,
            complex_name="잠실엘스",
            limit=1,
            sort_order="oldest",
        )

        rows = dao.find_trade_history(criteria)

        assert rows[0]["deal_date"] == "2025-01-10"


def test_dao_can_return_price_order_lowest():
    with make_session() as session:
        dao = SimpleLookupDao(session)
        criteria = SimpleLookupCriteria(
            query_type=QUERY_TRADE,
            complex_name="잠실엘스",
            price_order="lowest",
        )

        rows = dao.find_record_price(criteria)

        assert rows[0]["deal_amount"] == 190000


def test_dao_resolves_missing_and_ambiguous_complexes():
    with make_session() as session:
        dao = SimpleLookupDao(session)

        missing = SimpleLookupCriteria(
            query_type=QUERY_LOCATION,
            complex_name="없는아파트",
        )
        ambiguous = SimpleLookupCriteria(
            query_type=QUERY_LOCATION,
            complex_name="현대아파트",
        )

        assert_lookup_error(
            "target_not_found",
            lambda: dao.find_location(missing),
        )
        error = assert_lookup_error(
            "ambiguous_target",
            lambda: dao.find_location(ambiguous),
        )
        assert [item["complex_id"] for item in error.candidates] == [102, 103]
        assert [item["trade_name"] for item in error.candidates] == [
            "현대아파트",
            "현대아파트",
        ]


def test_dao_searches_trade_name_without_duplicate_candidates_from_trades():
    with make_session() as session:
        dao = SimpleLookupDao(session)
        criteria = SimpleLookupCriteria(
            query_type=QUERY_LOCATION,
            complex_name="잠실엘스",
        )

        result = dao.find_location(criteria)

        assert len(result) == 1
        assert result[0]["complex_id"] == 101
        assert result[0]["trade_name"] == "잠실엘스"


def test_dao_resolves_common_apartment_suffix_alias():
    with make_session() as session:
        dao = SimpleLookupDao(session)
        criteria = SimpleLookupCriteria(
            query_type=QUERY_LOCATION,
            complex_name="은마아파트",
        )

        result = dao.find_location(criteria)

        assert result[0]["complex_id"] == 105
        assert result[0]["complex_name"] == "은마"


def test_dao_resolves_space_normalized_complex_name():
    with make_session() as session:
        dao = SimpleLookupDao(session)
        criteria = SimpleLookupCriteria(
            query_type=QUERY_LOCATION,
            complex_name="스카이 써밋",
        )

        result = dao.find_location(criteria)

        assert result[0]["complex_id"] == 106
        assert result[0]["complex_name"] == "스카이써밋아파트"


def test_dao_resolves_numbered_complex_name_without_spaces():
    with make_session() as session:
        dao = SimpleLookupDao(session)
        criteria = SimpleLookupCriteria(
            query_type=QUERY_LOCATION,
            complex_name="개포 5단지",
        )

        result = dao.find_location(criteria)

        assert result[0]["complex_id"] == 107
        assert result[0]["complex_name"] == "개포주공5단지"


def test_service_handles_all_query_types():
    with make_session() as session:
        service = SimpleLookupService(SimpleLookupDao(session))

        location = service.handle(
            SimpleLookupSlots(
                query_type=QUERY_LOCATION,
                complex_name="잠실엘스",
            )
        )
        history = service.handle(
            SimpleLookupSlots(
                query_type=QUERY_TRADE,
                complex_name="잠실엘스",
                area=84,
            )
        )
        high = service.handle(
            SimpleLookupSlots(
                query_type=QUERY_TRADE,
                complex_name="잠실엘스",
                price_order="highest",
            )
        )
        low = service.handle(
            SimpleLookupSlots(
                query_type=QUERY_TRADE,
                complex_name="잠실엘스",
                price_order="lowest",
            )
        )

        assert location.success is True
        assert location.data[0]["address"] == "서울 송파구 잠실동"
        assert [row["deal_amount"] for row in history.data] == [210000, 200000]
        assert high.data[0]["deal_amount"] == 210000
        assert low.data[0]["deal_amount"] == 190000


def test_service_converts_business_errors_but_not_database_errors():
    with make_session() as session:
        service = SimpleLookupService(SimpleLookupDao(session))

        invalid = service.handle(
            SimpleLookupSlots(
                query_type=QUERY_TRADE,
                complex_name="잠실엘스",
                area=84,
                pyeong=34,
            )
        )
        assert invalid.reason == "invalid_request"

        def broken_search(_complex_name: str):
            raise RuntimeError("database unavailable")

        service.dao._find_complexes = broken_search

        with pytest.raises(RuntimeError, match="database unavailable"):
            service.handle(
                SimpleLookupSlots(
                    query_type=QUERY_LOCATION,
                    complex_name="잠실엘스",
                )
            )


def test_run_simple_lookup_returns_same_result_shape_for_validation_errors():
    with make_session() as session:
        result = run_simple_lookup(
            session,
            {"query_type": QUERY_LOCATION},
        )

        assert result["handler"] == "simple_lookup"
        assert result["success"] is False
        assert result["reason"] == "invalid_request"
        assert result["criteria"] == {}
        assert result["data"] == []
        assert result["candidates"] == []
