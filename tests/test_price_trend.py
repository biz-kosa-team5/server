from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from app.chatbot.features.price_trend import (
    ANALYSIS_RANKING,
    ANALYSIS_TIMESERIES,
    TARGET_COMPLEX,
    TARGET_REGION,
    PriceTrendPolicy,
    TrendError,
    TrendService,
    TrendSlots,
    extract_price_trend_slots,
    run_price_trend,
)
from app.database import SessionLocal, ensure_initialized


def slots(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "analysis_type": ANALYSIS_TIMESERIES,
        "target_type": TARGET_REGION,
        "target_name": "Gangnam-gu",
    }
    values.update(overrides)
    return values


class FakeTrendDao:
    def __init__(
        self,
        *,
        timeseries_rows: list[dict[str, Any]] | None = None,
        ranking_rows: list[dict[str, Any]] | None = None,
        error: TrendError | None = None,
    ) -> None:
        self.timeseries_rows = timeseries_rows or []
        self.ranking_rows = ranking_rows or []
        self.error = error
        self.calls: list[tuple[str, Any, dict[str, Any]]] = []

    def find_timeseries(self, session: Any, criteria: dict[str, Any]) -> list[dict[str, Any]]:
        self.calls.append(("timeseries", session, criteria))
        if self.error is not None:
            raise self.error
        return self.timeseries_rows

    def find_ranking(self, session: Any, criteria: dict[str, Any]) -> list[dict[str, Any]]:
        self.calls.append(("ranking", session, criteria))
        if self.error is not None:
            raise self.error
        return self.ranking_rows


def test_slots_accept_single_target_name():
    item = TrendSlots(
        analysis_type=ANALYSIS_TIMESERIES,
        target_type=TARGET_COMPLEX,
        target_name="Eunma",
    )

    assert item.target_name == "Eunma"


def test_policy_builds_timeseries_criteria_with_minimum_rules():
    criteria = PriceTrendPolicy(base_date=date(2025, 12, 31)).build_criteria(
        slots(target_type=TARGET_COMPLEX, target_name="Eunma", pyeong=34, period="1y")
    )

    assert criteria["analysis_type"] == ANALYSIS_TIMESERIES
    assert criteria["target_type"] == TARGET_COMPLEX
    assert criteria["target_name"] == "Eunma"
    assert criteria["interval"] == "month"
    assert criteria["start_date"] == date(2025, 1, 1)
    assert criteria["end_date"] == date(2025, 12, 31)
    assert criteria["area_min"] == pytest.approx(81.2979)
    assert criteria["area_max"] == pytest.approx(87.2979)


def test_policy_builds_default_ranking_criteria():
    criteria = PriceTrendPolicy(base_date=date(2025, 12, 31)).build_criteria(
        slots(analysis_type=ANALYSIS_RANKING)
    )

    assert criteria["analysis_type"] == ANALYSIS_RANKING
    assert criteria["rank_by"] == "change_rate"
    assert criteria["direction"] == "desc"
    assert criteria["limit"] == 5


@pytest.mark.parametrize(
    "bad_slots",
    [
        slots(interval="week"),
        slots(area=84, pyeong=34),
        slots(analysis_type=ANALYSIS_RANKING, rank_by="max_deal_amount"),
        slots(limit=0, analysis_type=ANALYSIS_RANKING),
    ],
)
def test_policy_rejects_bad_inputs(bad_slots: dict[str, Any]):
    with pytest.raises(TrendError):
        PriceTrendPolicy(base_date=date(2025, 12, 31)).build_criteria(bad_slots)


def test_period_extractor_keeps_original_question():
    result = extract_price_trend_slots("Eunma recent price trend")

    assert result == {"original_question": "Eunma recent price trend"}


@pytest.mark.parametrize(
    "query",
    [
        "잠실엘스 최근 1년 시세추이",
        "경덕 아파트 2015년부터 월별 시세추이",
        "경덕아파트 2015년 시세추이",
        "은마 2018년부터 2022년까지 시세추이",
        "경덕아파트 10년간 시세추이",
        "강남구에서 많이 오른 아파트 TOP 5",
        "강남 3구에서 많이 오른 아파트",
    ],
)
def test_period_extractor_preserves_only_original_question_for_korean_queries(query: str):
    result = extract_price_trend_slots(query)

    assert result == {"original_question": query}


def test_service_returns_timeseries_observation():
    dao = FakeTrendDao(
        timeseries_rows=[
            {
                "period_start": "2025-01-01",
                "avg_deal_amount": 100000,
                "avg_price_per_sqm": 1190.48,
                "trade_count": 2,
            }
        ]
    )
    result = TrendService(
        dao=dao,
        policy=PriceTrendPolicy(base_date=date(2025, 12, 31)),
    ).handle(object(), slots(target_type=TARGET_COMPLEX, target_name="Eunma", period="1y"))

    assert result["handler"] == "price_trend"
    assert result["success"] is True
    assert result["observation_type"] == ANALYSIS_TIMESERIES
    assert result["criteria"]["target_name"] == "Eunma"
    assert result["row_count"] == 1
    assert result["summary_metrics"] == {
        "row_count": 1,
        "first_period": "2025-01-01",
        "last_period": "2025-01-01",
        "first_avg_deal_amount": 100000,
        "last_avg_deal_amount": 100000,
        "first_avg_price_per_sqm": 1190.48,
        "last_avg_price_per_sqm": 1190.48,
        "first_trade_count": 2,
        "last_trade_count": 2,
        "total_trade_count": 2,
    }
    assert result["rows"][0]["trade_count"] == 2
    assert dao.calls[0][0] == "timeseries"


def test_service_returns_ranking_observation():
    dao = FakeTrendDao(
        ranking_rows=[
            {
                "rank": 1,
                "complex_id": 10,
                "complex_name": "Raemian",
                "change_rate": 20.0,
            }
        ]
    )
    result = TrendService(
        dao=dao,
        policy=PriceTrendPolicy(base_date=date(2025, 12, 31)),
    ).handle(object(), slots(analysis_type=ANALYSIS_RANKING, direction="desc", limit=3))

    assert result["success"] is True
    assert result["observation_type"] == ANALYSIS_RANKING
    assert result["criteria"]["limit"] == 3
    assert result["rows"][0]["complex_name"] == "Raemian"
    assert dao.calls[0][0] == "ranking"


def test_service_returns_no_result_failure():
    result = TrendService(
        dao=FakeTrendDao(),
        policy=PriceTrendPolicy(base_date=date(2025, 12, 31)),
    ).handle(object(), slots())

    assert result["handler"] == "price_trend"
    assert result["success"] is False
    assert result["reason"] == "no_result"
    assert result["rows"] == []


def test_service_returns_trend_error_failure_with_candidates():
    error = TrendError(
        "target_not_found",
        "target was not found",
        candidates=[{"name": "Eunma"}],
    )
    result = TrendService(
        dao=FakeTrendDao(error=error),
        policy=PriceTrendPolicy(base_date=date(2025, 12, 31)),
    ).handle(object(), slots(target_type=TARGET_COMPLEX, target_name="Unknown"))

    assert result["success"] is False
    assert result["reason"] == "target_not_found"
    assert result["message"] == "target was not found"
    assert result["candidates"] == [{"name": "Eunma"}]


def test_validation_error_response():
    result = TrendService(
        dao=FakeTrendDao(),
        policy=PriceTrendPolicy(base_date=date(2025, 12, 31)),
    ).handle(object(), {"analysis_type": "unknown", "target_type": "region", "target_name": "Gangnam-gu"})

    assert result["handler"] == "price_trend"
    assert result["success"] is False
    assert result["reason"] == "invalid_request"


def test_price_trend_timeseries_runs_against_sqlite_fixture():
    ensure_initialized()

    with SessionLocal() as session:
        result = run_price_trend(session, {
            "analysis_type": ANALYSIS_TIMESERIES,
            "target_type": TARGET_COMPLEX,
            "target_name": "잠실엘스",
            "period": "1y",
        })

    assert result["handler"] == "price_trend"
    assert result["success"] is True
    assert result["observation_type"] == ANALYSIS_TIMESERIES
    assert result["criteria"]["target_name"] == "잠실엘스"
    assert result["row_count"] >= 1


def test_price_trend_ranking_runs_against_sqlite_fixture():
    ensure_initialized()

    with SessionLocal() as session:
        result = run_price_trend(session, {
            "analysis_type": ANALYSIS_RANKING,
            "target_type": TARGET_REGION,
            "target_name": "강남구",
            "period": "1y",
            "rank_by": "change_rate",
            "direction": "desc",
            "limit": 5,
        })

    assert result["handler"] == "price_trend"
    assert result["observation_type"] == ANALYSIS_RANKING
    assert result["criteria"]["target_name"] == "강남구"
