from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.orm import Session

from app.chatbot.features.complex_resolver import (
  AMBIGUOUS,
  INSUFFICIENT_QUERY,
  RESOLVED,
  ComplexResolver,
  complex_name_variants,
)
from app.chatbot.features.comparison.service import run_comparison
from app.chatbot.features.comparison.slots import extract_compare_slots
from app.chatbot.features.price_trend.dto import ANALYSIS_TIMESERIES, TARGET_COMPLEX
from app.chatbot.features.price_trend.service import run_price_trend
from app.chatbot.features.simple_lookup.dto import QUERY_LOCATION
from app.chatbot.features.simple_lookup.service import run_simple_lookup
from app.database import SessionLocal, ensure_initialized
from app.models import Complex


DAECHI_WOOSUNG_ID = 991001
CHEONGDAM_WOOSUNG_ID = 991002
JAMSIL_WOOSUNG_ID = 991003
GAEPO_WOOSUNG1_ID = 991004
SAMSUNG3_ID = 991005


@contextmanager
def seeded_resolver_session() -> Iterator[Session]:
  ensure_initialized()
  with SessionLocal() as session:
    session.add_all([
      Complex(
        id=DAECHI_WOOSUNG_ID,
        region_id=11680,
        parcel_id=991001,
        pnu="1168010600100630000",
        name="대치우성아파트",
        trade_name="대치우성",
        address="서울특별시 강남구 대치동 63",
        latitude=37.4977,
        longitude=127.0602,
      ),
      Complex(
        id=CHEONGDAM_WOOSUNG_ID,
        region_id=11680,
        parcel_id=991002,
        pnu="1168010400100110025",
        name="청담우성아파트",
        trade_name="청담우성",
        address="서울특별시 강남구 청담동 11-25",
        latitude=37.5217,
        longitude=127.0468,
      ),
      Complex(
        id=JAMSIL_WOOSUNG_ID,
        region_id=11710,
        parcel_id=991003,
        pnu="1171010100101010000",
        name="잠실우성아파트",
        trade_name="잠실우성",
        address="서울특별시 송파구 잠실동 101",
        latitude=37.512,
        longitude=127.082,
      ),
      Complex(
        id=GAEPO_WOOSUNG1_ID,
        region_id=11680,
        parcel_id=991004,
        pnu="1168010600105030000",
        name="개포우성1",
        trade_name="개포우성1",
        address="서울특별시 강남구 대치동 503",
        latitude=37.4915,
        longitude=127.0597,
      ),
      Complex(
        id=SAMSUNG3_ID,
        region_id=11680,
        parcel_id=991005,
        pnu="1168010600110160002",
        name="삼성3차",
        trade_name="삼성3차",
        address="서울특별시 강남구 대치동 1016-2",
        latitude=37.4976,
        longitude=127.0601,
      ),
    ])
    session.flush()
    try:
      yield session
    finally:
      session.rollback()


def test_complex_name_variants_expand_apartment_suffix_and_phase():
  assert complex_name_variants("우성 아파트")[:2] == ["우성아파트", "우성"]
  assert {"우성1차", "우성1", "우성"}.issubset(set(complex_name_variants("우성1차")))
  assert {"삼성3차아파트", "삼성3차", "삼성3"}.issubset(set(complex_name_variants("삼성 3차 아파트")))


def test_resolver_keeps_same_candidates_for_spaced_apartment_suffix():
  with seeded_resolver_session() as session:
    resolver = ComplexResolver(session)
    compact = resolver.resolve("우성아파트")
    spaced = resolver.resolve("우성 아파트")

  assert compact.status == AMBIGUOUS
  assert spaced.status == AMBIGUOUS
  assert {item["complex_id"] for item in compact.candidates} == {item["complex_id"] for item in spaced.candidates}


def test_resolver_uses_phase_fallback_without_losing_candidates():
  with seeded_resolver_session() as session:
    result = ComplexResolver(session).resolve("우성1차")

  assert result.status in {AMBIGUOUS, RESOLVED}
  assert any(item["matched_variant"] in {"우성1차", "우성1", "우성"} for item in result.candidates)
  assert any(item["complex_id"] == GAEPO_WOOSUNG1_ID for item in result.candidates)


def test_resolver_resolves_samsung_third_phase_apartment():
  with seeded_resolver_session() as session:
    result = ComplexResolver(session).resolve("삼성 3차 아파트")
    resolved_id = result.complex.id if result.complex is not None else None

  assert result.status == RESOLVED
  assert resolved_id == SAMSUNG3_ID


def test_resolver_rejects_generic_apartment_query_without_db_scan():
  with seeded_resolver_session() as session:
    result = ComplexResolver(session).resolve("아파트 찾아줘")

  assert result.status == INSUFFICIENT_QUERY
  assert result.candidates == []


def test_simple_lookup_returns_ambiguous_candidates_instead_of_not_found():
  with seeded_resolver_session() as session:
    result = run_simple_lookup(
      session,
      {
        "query_type": QUERY_LOCATION,
        "target_name": "우성 아파트",
      },
      "우성 아파트 찾아줘",
    )

  assert result["success"] is False
  assert result["reason"] == "ambiguous_target"
  assert result["reason"] != "target_not_found"
  assert len(result["candidates"]) >= 3
  assert all("complex_id" in item and "complex_name" in item for item in result["candidates"])


def test_price_trend_ambiguous_complex_returns_candidates():
  with seeded_resolver_session() as session:
    result = run_price_trend(
      session,
      {
        "analysis_type": ANALYSIS_TIMESERIES,
        "target_type": TARGET_COMPLEX,
        "target_name": "우성 아파트",
        "period": "1y",
      },
    )

  assert result["success"] is False
  assert result["reason"] == "ambiguous_target"
  assert len(result["candidates"]) >= 3


def test_comparison_uses_confirmed_target_as_anchor_with_resolution_note():
  question = "우성 아파트랑 삼성 3차 아파트 비교해줘"
  with seeded_resolver_session() as session:
    result = run_comparison(session, extract_compare_slots(question), question)

  assert result["success"] is True, result
  assert result["candidateGroups"] == []
  assert "삼성3차" in result["resolvedApartmentNames"]
  assert "대치우성아파트" in result["resolvedApartmentNames"]
  assert result["resolutionNotes"]
  assert any("가까운 후보" in note for note in result["resolutionNotes"])


def test_comparison_returns_candidate_groups_when_anchor_cannot_resolve():
  with seeded_resolver_session() as session:
    result = run_comparison(
      session,
      {"apartment_names": ["우성 아파트", "미존재파크"]},
      "우성 아파트랑 미존재파크 비교해줘",
    )

  assert result["success"] is False
  assert result["candidateGroups"]
  assert result["candidateGroups"][0]["input"] == "우성 아파트"
  assert result["missingApartmentNames"] == ["미존재파크"]
