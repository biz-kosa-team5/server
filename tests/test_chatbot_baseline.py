from app.chatbot.features.comparison import extract_compare_slots
from app.chatbot.features.recommendation import extract_recommendation_slots
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


def test_recommendation_extractor_keeps_school_shorthand_when_tokenized():
  slots = extract_recommendation_slots("초/중/고 가까운 강남구 아파트 3개 추천해줘")

  assert slots["school_types"] == ["초등학교", "중학교", "고등학교"]
  assert slots["radius_m"] == 800
  assert slots["limit"] == 3


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


def test_price_trend_tool_accepts_query_only_for_clear_timeseries_question(monkeypatch):
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
    "query": "잠실엘스 최근 1년 시세추이",
  })

  assert result["handler"] == "price_trend"
  assert result["success"] is True
  assert result["observation_type"] == "timeseries"
  assert captured["slots"]["analysis_type"] == "timeseries"
  assert captured["slots"]["target_type"] == "complex"
  assert captured["slots"]["target_name"] == "잠실엘스"
  assert captured["slots"]["period"] == "1y"
  assert result["rows"]


def test_price_trend_tool_accepts_query_only_for_clear_ranking_question(monkeypatch):
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
    "query": "강남구에서 많이 오른 아파트 TOP 5",
  })

  assert result["handler"] == "price_trend"
  assert result["success"] is True
  assert result["observation_type"] == "ranking"
  assert captured["slots"]["analysis_type"] == "ranking"
  assert captured["slots"]["target_type"] == "region"
  assert captured["slots"]["target_name"] == "강남구"
  assert captured["slots"]["direction"] == "desc"
  assert captured["slots"]["limit"] == 5
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
