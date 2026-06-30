from app.chatbot.features.comparison import extract_compare_slots, run_comparison
from app.chatbot.features.recommendation import extract_recommendation_slots, run_recommendation
from app.chatbot.service.answer.formatters.comparison import format_comparison_result
from app.chatbot.service.answer.formatters.recommendation import format_recommendation_result
from app.chatbot.service.tools import (
  build_comparison_tool,
  build_legal_contract_tool,
  build_price_trend_tool,
  build_recommendation_tool,
  build_simple_lookup_tool,
)
from app.database import SessionLocal, ensure_initialized
from app.models import Complex


def test_recommendation_extractor_builds_filter_slots():
  slots = extract_recommendation_slots("서초역 근처 30억 이하 신축 아파트 추천해줘")

  assert slots["station_name"] == "서초역"
  assert slots["max_price"] == 300000
  assert slots["is_new_build"] is True
  assert slots["min_built_year"] == 2020
  assert slots["radius_m"] == 800
  assert slots["sort_by"] == "distance_asc"


def test_recommendation_extractor_does_not_treat_connector_go_as_high_school():
  slots = extract_recommendation_slots("강남구에 있는 아파트 3개를 추천해주고 그 이유를 알려줘")

  assert slots == {
    "district": "강남구",
    "limit": 3,
  }


def test_recommendation_extractor_builds_neighborhood_slot():
  slots = extract_recommendation_slots("송파구 잠실동 아파트 3개 추천해줘")

  assert slots["district"] == "송파구"
  assert slots["neighborhood"] == "잠실동"
  assert slots["limit"] == 3


def test_recommendation_filters_by_neighborhood():
  ensure_initialized()
  with SessionLocal() as session:
    result = run_recommendation(session, {"neighborhood": "잠실동", "limit": 5}, "잠실동 아파트 추천해줘")

  assert result["success"] is True, result
  assert result["results"]
  assert all("잠실동" in item["address"] for item in result["results"])


def test_recommendation_prefers_candidates_with_infrastructure_by_default():
  ensure_initialized()
  with SessionLocal() as session:
    result = run_recommendation(session, {"neighborhood": "대치동", "limit": 5}, "대치동 아파트 추천해줘")

  assert result["success"] is True
  first = result["results"][0]
  assert first["latitude"] is not None
  assert first["longitude"] is not None
  assert first["infrastructure"]["nearestStation"] is not None
  assert first["infrastructure"]["nearestEducation"] is not None


def test_recommendation_does_not_fallback_to_other_regions_for_unknown_neighborhood():
  ensure_initialized()
  with SessionLocal() as session:
    result = run_recommendation(session, {"neighborhood": "없는동", "limit": 5}, "없는동 아파트 추천해줘")

  assert result["success"] is False
  assert result["results"] == []


def test_recommendation_extractor_keeps_school_shorthand_when_tokenized():
  slots = extract_recommendation_slots("초/중/고 가까운 강남구 아파트 3개 추천해줘")

  assert slots["school_types"] == ["초등학교", "중학교", "고등학교"]
  assert slots["radius_m"] == 800
  assert slots["limit"] == 3


def test_recommendation_extractor_handles_short_school_nearby_query():
  slots = extract_recommendation_slots("초등학교근처")

  assert slots["school_type"] == "초등학교"
  assert slots["radius_m"] == 800
  assert slots["sort_by"] == "school_distance_asc"
  assert slots["infra_preferences"] == ["education"]


def test_recommendation_extractor_keeps_district_and_price_words_distinct():
  cheap_slots = extract_recommendation_slots("서초구 20억 이하 저렴한 아파트 4곳 추천해줘")
  expensive_slots = extract_recommendation_slots("청담역 주변 비싼 아파트 3개 추천해줘")

  assert cheap_slots["district"] == "서초구"
  assert cheap_slots["limit"] == 4
  assert cheap_slots["sort_by"] == "price_asc"
  assert "school_type" not in cheap_slots
  assert expensive_slots["station_name"] == "청담역"
  assert expensive_slots["sort_by"] == "price_desc"


def test_comparison_extractor_builds_subject_and_metric_slots():
  slots = extract_compare_slots("래미안대치팰리스랑 잠실엘스 가격 비교해줘")

  assert slots["apartment_names"] == ["래미안대치팰리스", "잠실엘스"]
  assert slots["metrics"] == ["latest_price", "pyeong", "price_per_pyeong"]


def test_comparison_extractor_accepts_comma_separated_names():
  slots = extract_compare_slots("잠실엘스, 래미안대치펠리스 비교해봐")

  assert slots["apartment_names"] == ["잠실엘스", "래미안대치펠리스"]


def test_comparison_extractor_removes_leading_discourse_marker():
  assert extract_compare_slots("그럼은마아파트랑 선경 아파트 비교해줘")["apartment_names"] == [
    "은마아파트",
    "선경 아파트",
  ]
  assert extract_compare_slots("그러면 은마아파트랑 선경 아파트 비교해줘")["apartment_names"] == [
    "은마아파트",
    "선경 아파트",
  ]


def test_comparison_extractor_cleans_metric_words_from_names():
  assert extract_compare_slots("반포자이랑 래미안퍼스티지 초등학교 접근성 비교해줘")["apartment_names"] == [
    "반포자이",
    "래미안퍼스티지",
  ]
  assert extract_compare_slots("아크로리버파크랑 래미안원펜타스 가격이랑 평당가 비교해줘")["apartment_names"] == [
    "아크로리버파크",
    "래미안원펜타스",
  ]
  assert extract_compare_slots("도곡렉슬이랑 대치현대 어디가 더 대단지야 비교해줘")["apartment_names"] == [
    "도곡렉슬",
    "대치현대",
  ]
  assert extract_compare_slots("잠실엘스랑 리센츠 상권 학군 미래 가격 전망 비교해줘")["apartment_names"] == [
    "잠실엘스",
    "리센츠",
  ]
  assert extract_compare_slots("잠실엘스랑 리센츠 재개발 전망 비교해줘")["apartment_names"] == [
    "잠실엘스",
    "리센츠",
  ]
  assert extract_compare_slots("래미안대치팰리스랑 잠실엘스 중 어디가 초등학교에 가까워?")["apartment_names"] == [
    "래미안대치팰리스",
    "잠실엘스",
  ]


def test_comparison_name_lookup_accepts_palace_spelling_variant():
  ensure_initialized()
  with SessionLocal() as session:
    result = run_comparison(
      session,
      extract_compare_slots("잠실엘스, 래미안대치펠리스 비교해봐"),
      "잠실엘스, 래미안대치펠리스 비교해봐",
    )

  assert result["success"] is True, result
  assert result["missingApartmentNames"] == []
  assert [row["complexName"] for row in result["results"]] == ["잠실엘스", "래미안대치팰리스"]


def test_comparison_name_lookup_accepts_minor_typo():
  ensure_initialized()
  with SessionLocal() as session:
    result = run_comparison(
      session,
      extract_compare_slots("레미안대치팰리스랑 잠실엘스 비교해줘"),
      "레미안대치팰리스랑 잠실엘스 비교해줘",
    )

  assert result["success"] is True, result
  assert result["missingApartmentNames"] == []
  assert [row["complexName"] for row in result["results"]] == ["래미안대치팰리스", "잠실엘스"]


def test_comparison_name_lookup_normalizes_spacing_and_spelling_variant():
  ensure_initialized()
  with SessionLocal() as session:
    session.add(
      Complex(
        id=990901,
        region_id=11680,
        parcel_id=9909001,
        pnu="1168010600199090001",
        name="테스트 레이크 팰리스",
        trade_name="테스트 레이크 팰리스",
        address="서울특별시 강남구 대치동 990",
        latitude=37.4984,
        longitude=127.0632,
      )
    )
    session.flush()

    question = "테스트레이크펠리스랑 잠실엘스 중 어디가 초등학교에 가까워?"
    result = run_comparison(session, extract_compare_slots(question), question)
    session.rollback()

  assert result["success"] is True, result
  assert result["missingApartmentNames"] == []
  assert result["criteria"]["school_type"] == "초등학교"
  assert [row["complexName"] for row in result["results"]] == ["테스트 레이크 팰리스", "잠실엘스"]
  assert all(row["nearestSchool"] is not None for row in result["results"])


def test_comparison_infers_names_without_explicit_separator():
  ensure_initialized()
  with SessionLocal() as session:
    spaced_result = run_comparison(
      session,
      extract_compare_slots("잠실엘스 래미안대치팰리스 비교해줘"),
      "잠실엘스 래미안대치팰리스 비교해줘",
    )
    joined_result = run_comparison(
      session,
      extract_compare_slots("잠실엘스래미안대치팰리스 비교해줘"),
      "잠실엘스래미안대치팰리스 비교해줘",
    )

  assert spaced_result["success"] is True, spaced_result
  assert joined_result["success"] is True, joined_result
  assert spaced_result["criteria"]["apartment_names"] == ["잠실엘스", "래미안대치팰리스"]
  assert joined_result["criteria"]["apartment_names"] == ["잠실엘스", "래미안대치팰리스"]


def test_comparison_accepts_apartment_suffix_and_school_closeness_phrase():
  q = "은마아파트랑 잠실엘스 중 초등학교가 더 가까운 곳 비교"
  slots = extract_compare_slots(q)

  assert slots["apartment_names"] == ["은마아파트", "잠실엘스"]
  assert slots["metrics"] == ["nearest_school"]
  assert slots["school_type"] == "초등학교"


def test_recommendation_answer_includes_lifestyle_and_redevelopment_context():
  answer = format_recommendation_result({
    "handler": "recommendation",
    "success": True,
    "criteria": {"district": "송파구"},
    "results": [{
      "complexName": "잠실엘스",
      "latestDealAmountText": "25.0억원",
      "unitCnt": 5678,
      "useDate": "2008-09-01",
      "infrastructure": {
        "nearbyLifestyle": [
          {"name": "롯데백화점 잠실점", "subtype": "백화점", "distanceM": 620},
          {"name": "서울아산병원", "subtype": "병원", "distanceM": 780},
        ],
      },
      "redevelopmentInfo": [{"title": "잠실 일대 정비사업 관련 기사", "url": "https://example.com"}],
    }],
  })

  assert "800m 생활편의" in answer
  assert "롯데백화점 잠실점" in answer
  assert "재개발/정비사업 검색결과" in answer
  assert "상권이나 학군 평판처럼 데이터에 없는" not in answer


def test_recommendation_answer_mentions_missing_redevelopment_context():
  answer = format_recommendation_result({
    "handler": "recommendation",
    "success": True,
    "criteria": {"neighborhood": "대치동"},
    "results": [{
      "complexName": "대치테스트",
      "latestDealAmountText": "12.0억원",
      "infrastructure": {
        "nearestStation": {"name": "한티역", "distanceM": 300},
        "nearestEducation": {"name": "서울도곡초등학교", "distanceM": 200},
        "nearbyLifestyle": [],
      },
      "redevelopmentInfo": [],
    }],
  })

  assert "한티역" in answer
  assert "서울도곡초등학교" in answer
  assert "현재 응답 데이터에서 확인된 재개발/정비사업 정보는 없습니다" in answer


def test_comparison_answer_includes_lifestyle_and_redevelopment_context():
  answer = format_comparison_result({
    "handler": "comparison",
    "success": True,
    "criteria": {"apartment_names": ["잠실엘스", "리센츠"]},
    "results": [
      {
        "complexName": "잠실엘스",
        "latestDealAmountText": "25.0억원",
        "unitCnt": 5678,
        "builtYear": 2008,
        "nearbyLifestyle": [{"name": "롯데백화점 잠실점", "subtype": "백화점", "distanceM": 620}],
        "redevelopmentInfo": [{"title": "잠실 일대 정비사업 관련 기사", "url": "https://example.com"}],
      },
      {
        "complexName": "리센츠",
        "latestDealAmountText": "24.0억원",
        "unitCnt": 5563,
        "builtYear": 2008,
        "nearbyLifestyle": [{"name": "서울아산병원", "subtype": "병원", "distanceM": 780}],
        "redevelopmentInfo": [],
      },
    ],
    "missingApartmentNames": [],
  })

  assert "800m 생활편의" in answer
  assert "롯데백화점 잠실점" in answer
  assert "재개발/정비사업 검색결과" in answer
  assert "상권, 학군 평판, 미래 가격 전망은 제공된 데이터만으로는 확인할 수 없습니다." not in answer


def test_simple_lookup_tool_calls_existing_service():
  ensure_initialized()
  with SessionLocal() as session:
    result = build_simple_lookup_tool(session).invoke({"query": "잠실엘스 어디 있어?"})

  assert result["handler"] == "simple_lookup"
  assert result["success"] is True
  assert result["query_type"] == "location"


def test_simple_lookup_tool_overrides_extracted_slots():
  ensure_initialized()
  with SessionLocal() as session:
    result = build_simple_lookup_tool(session).invoke({
      "query": "잠실 엘스 시세 알려줘",
      "query_type": "location",
      "target_name": "잠실엘스",
    })

  assert result["handler"] == "simple_lookup"
  assert result["success"] is True
  assert result["query_type"] == "location"
  assert result["criteria"]["target_name"] == "잠실엘스"


def test_price_trend_tool_uses_llm_args_for_timeseries_question(monkeypatch):
  captured = {}

  def fake_run_price_trend(_session, slots):
    captured["slots"] = slots
    return {
      "handler": "price_trend",
      "success": True,
      "observation_type": "timeseries",
      "criteria": slots,
      "rows": [{"period_start": "2026-01-01"}],
    }

  monkeypatch.setattr("app.chatbot.service.tools.price_trend_tool.run_price_trend", fake_run_price_trend)

  result = build_price_trend_tool(object()).invoke({
    "query": "Eunma recent price trend",
    "analysis_type": "timeseries",
    "target_type": "complex",
    "target_name": "Eunma",
    "period": "1y",
  })

  assert result["handler"] == "price_trend"
  assert result["success"] is True
  assert result["observation_type"] == "timeseries"
  assert captured["slots"]["analysis_type"] == "timeseries"
  assert captured["slots"]["target_type"] == "complex"
  assert captured["slots"]["target_name"] == "Eunma"
  assert captured["slots"]["period"] == "1y"
  assert captured["slots"]["original_question"] == "Eunma recent price trend"
  assert result["rows"]


def test_price_trend_tool_uses_llm_args_for_ranking_question(monkeypatch):
  captured = {}

  def fake_run_price_trend(_session, slots):
    captured["slots"] = slots
    return {
      "handler": "price_trend",
      "success": True,
      "observation_type": "ranking",
      "criteria": slots,
      "rows": [{"rank": 1}],
    }

  monkeypatch.setattr("app.chatbot.service.tools.price_trend_tool.run_price_trend", fake_run_price_trend)

  result = build_price_trend_tool(object()).invoke({
    "query": "Gangnam-gu top movers",
    "analysis_type": "ranking",
    "target_type": "region",
    "target_name": "Gangnam-gu",
    "rank_by": "change_rate",
    "direction": "desc",
    "limit": 5,
  })

  assert result["handler"] == "price_trend"
  assert result["success"] is True
  assert result["observation_type"] == "ranking"
  assert captured["slots"]["analysis_type"] == "ranking"
  assert captured["slots"]["target_type"] == "region"
  assert captured["slots"]["target_name"] == "Gangnam-gu"
  assert captured["slots"]["rank_by"] == "change_rate"
  assert captured["slots"]["direction"] == "desc"
  assert captured["slots"]["limit"] == 5
  assert captured["slots"]["original_question"] == "Gangnam-gu top movers"
  assert result["rows"]


def test_feature_tools_are_langchain_tools():
  ensure_initialized()
  with SessionLocal() as session:
    tools = [
      build_simple_lookup_tool(session),
      build_recommendation_tool(session),
      build_comparison_tool(session),
      build_price_trend_tool(session),
      build_legal_contract_tool(session),
    ]

  assert [tool.name for tool in tools] == [
    "simple_lookup",
    "recommend_apartments",
    "compare_apartments",
    "analyze_price_trend",
    "search_legal_contract",
  ]
  assert all(tool.description for tool in tools)
