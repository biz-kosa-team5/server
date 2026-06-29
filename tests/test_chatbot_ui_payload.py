from __future__ import annotations

from app.chatbot.service.ui_payload import build_chatbot_ui_payload
from app.database import SessionLocal, ensure_initialized


def payload_for(result: dict) -> dict:
  return {
    "success": result.get("success") is True,
    "status": "success" if result.get("success") is True else "failed",
    "question": "잠실엘스 위치 알려줘",
    "fragments": [
      {
        "index": 0,
        "text": "잠실엘스 위치 알려줘",
        "status": "handled" if result.get("success") is True else "not_handled",
        "result": result,
      }
    ],
    "result": result,
    "message": "질문을 처리했습니다.",
    "executionSummary": {"total": 1, "succeeded": 1, "failed": 0},
  }


def build(result: dict) -> dict:
  ensure_initialized()
  with SessionLocal() as session:
    return build_chatbot_ui_payload(session, payload_for(result))


def test_location_lookup_builds_focus_map_action():
  ui_payload = build({
    "handler": "simple_lookup",
    "success": True,
    "query_type": "location",
    "data": [
      {
        "complex_id": 1002,
        "complex_name": "잠실엘스",
        "latitude": 37.5124,
        "longitude": 127.0821,
      }
    ],
  })

  assert ui_payload["uiActions"][0]["id"] == "focus_map:complex:1002"
  assert ui_payload["uiActions"][0]["autoRun"] is True
  assert ui_payload["uiActions"][0]["priority"] == "primary"
  assert ui_payload["uiActions"][0]["target"] == {
    "kind": "complex",
    "name": "잠실엘스",
    "complexId": 1002,
    "parcelId": 9001002,
    "latitude": 37.5124,
    "longitude": 127.0821,
    "level": 2,
    "openDetail": True,
  }
  assert ui_payload["uiSummary"]["hasMapFocus"] is True
  assert ui_payload["uiSummary"]["primaryTargetName"] == "잠실엘스"


def test_trade_history_resolves_complex_coordinates_from_db():
  ui_payload = build({
    "handler": "simple_lookup",
    "success": True,
    "query_type": "trade_history",
    "data": [
      {
        "complex_id": 1002,
        "complex_name": "잠실엘스",
        "deal_amount": 330000,
      }
    ],
  })

  action = ui_payload["uiActions"][0]
  assert action["source"] == "simple_lookup.trade_history"
  assert action["target"]["latitude"] == 37.5124
  assert action["target"]["longitude"] == 127.0821
  assert action["target"]["openDetail"] is True


def test_region_price_ranking_builds_actions_and_ranking_artifact():
  ui_payload = build({
    "handler": "simple_lookup",
    "success": True,
    "query_type": "region_price_ranking",
    "criteria": {
      "target_name": "강남구",
      "price_order": "highest",
    },
    "data": [
      {
        "rank": 1,
        "region_name": "강남구",
        "complex_id": 1001,
        "complex_name": "래미안대치팰리스",
        "deal_amount": 435000,
      },
      {
        "rank": 2,
        "region_name": "강남구",
        "complex_id": 1004,
        "complex_name": "강남센트럴아이파크",
        "deal_amount": 250000,
      },
    ],
  })

  assert [action["id"] for action in ui_payload["uiActions"]] == [
    "focus_map:complex:1001",
    "focus_map:complex:1004",
  ]
  assert ui_payload["uiActions"][0]["autoRun"] is True
  ranking = ui_payload["uiArtifacts"][0]
  assert ranking["type"] == "ranking_list"
  assert ranking["items"][0]["metricValue"] == "43.5억원"
  assert ranking["items"][0]["actionId"] == "focus_map:complex:1001"


def test_recommendation_builds_limited_actions_and_list_artifact():
  ui_payload = build({
    "handler": "recommendation",
    "success": True,
    "criteria": {"district": "송파구"},
    "results": [
      recommendation_item(1002, "잠실엘스", 37.5124, 127.0821, "31.0억원"),
      recommendation_item(1001, "래미안대치팰리스", 37.4988, 127.0652, "43.5억원"),
      recommendation_item(1004, "강남센트럴아이파크", 37.4847, 127.0666, "25.0억원"),
      recommendation_item(9999, "초과 후보", 37.4, 127.0, "10.0억원"),
    ],
  })

  assert len(ui_payload["uiActions"]) == 3
  assert ui_payload["uiActions"][0]["id"] == "focus_map:complex:1002"
  artifact = ui_payload["uiArtifacts"][0]
  assert artifact["type"] == "recommendation_list"
  assert [item["name"] for item in artifact["items"]] == [
    "잠실엘스",
    "래미안대치팰리스",
    "강남센트럴아이파크",
  ]
  assert artifact["items"][0]["actionId"] == "focus_map:complex:1002"


def test_comparison_builds_bar_chart_with_filtered_metrics():
  ui_payload = build({
    "handler": "comparison",
    "success": True,
    "criteria": {
      "apartment_names": ["잠실엘스", "래미안대치팰리스"],
      "metrics": ["latest_price", "nearest_station"],
    },
    "results": [
      {
        "complexId": 1002,
        "complexName": "잠실엘스",
        "parcelId": 9001002,
        "latitude": 37.5124,
        "longitude": 127.0821,
        "latestDealAmount": 330000,
        "unitCnt": 5678,
        "nearestStation": {"name": "잠실새내역", "distanceM": 404},
      },
      {
        "complexId": 1001,
        "complexName": "래미안대치팰리스",
        "parcelId": 9001001,
        "latitude": 37.4988,
        "longitude": 127.0652,
        "latestDealAmount": 435000,
        "unitCnt": 1608,
        "nearestStation": {"name": "대치역", "distanceM": 320},
      },
    ],
  })

  artifact = ui_payload["uiArtifacts"][0]
  assert artifact["type"] == "comparison_bar_chart"
  assert artifact["defaultMetric"] == "nearestStationDistanceM"
  assert [metric["key"] for metric in artifact["metrics"]] == [
    "latestDealAmount",
    "unitCnt",
    "nearestStationDistanceM",
  ]
  assert artifact["items"][0]["values"]["latestDealAmount"] == 330000
  assert artifact["items"][0]["actionId"] == "focus_map:complex:1002"


def test_price_trend_timeseries_builds_action_and_trend_artifact():
  ui_payload = build({
    "handler": "price_trend",
    "success": True,
    "observation_type": "timeseries",
    "criteria": {
      "target_type": "complex",
      "target_name": "잠실엘스",
    },
    "row_count": 2,
    "rows": [
      {
        "period_start": "2026-05-01",
        "avg_deal_amount": 315000,
        "trade_count": 2,
      },
      {
        "period_start": "2025-06-01",
        "avg_deal_amount": 300000,
        "trade_count": 1,
      },
    ],
  })

  assert ui_payload["uiActions"][0]["id"] == "focus_map:complex:1002"
  artifact = ui_payload["uiArtifacts"][0]
  assert artifact["type"] == "trend_line_chart"
  assert artifact["points"] == [
    {"period": "2025-06", "value": 300000.0, "count": 1},
    {"period": "2026-05", "value": 315000.0, "count": 2},
  ]


def test_price_trend_region_timeseries_builds_region_focus():
  ui_payload = build({
    "handler": "price_trend",
    "success": True,
    "observation_type": "timeseries",
    "criteria": {
      "target_type": "region",
      "target_name": "강남구",
    },
    "row_count": 2,
    "rows": [
      {"period_start": "2025-01-01", "avg_price_per_sqm": 1000, "trade_count": 1},
      {"period_start": "2025-02-01", "avg_price_per_sqm": 1100, "trade_count": 1},
    ],
  })

  action = ui_payload["uiActions"][0]
  assert action["id"] == "focus_map:region:강남구"
  assert action["target"]["kind"] == "region"
  assert action["target"]["level"] == 7
  assert action["target"]["openDetail"] is False


def test_legal_and_no_matching_results_do_not_create_ui_payload():
  legal_payload = build({
    "handler": "legal_contract",
    "success": True,
    "sources": [],
  })
  no_matching_payload = build({
    "success": False,
    "reason": "no_matching_tool",
    "message": "지원하지 않는 질문입니다.",
  })

  assert legal_payload["uiActions"] == []
  assert legal_payload["uiArtifacts"] == []
  assert no_matching_payload["uiActions"] == []
  assert no_matching_payload["uiArtifacts"] == []


def test_duplicate_lookup_creates_one_action():
  response = {
    "success": True,
    "status": "success",
    "question": "잠실엘스 위치와 실거래 알려줘",
    "fragments": [
      {
        "index": 0,
        "text": "잠실엘스 위치 알려줘",
        "status": "handled",
        "result": {
          "handler": "simple_lookup",
          "success": True,
          "query_type": "location",
          "data": [{"complex_id": 1002, "complex_name": "잠실엘스", "latitude": 37.5124, "longitude": 127.0821}],
        },
      },
      {
        "index": 1,
        "text": "잠실엘스 실거래 알려줘",
        "status": "handled",
        "result": {
          "handler": "simple_lookup",
          "success": True,
          "query_type": "trade_history",
          "data": [{"complex_id": 1002, "complex_name": "잠실엘스", "deal_amount": 330000}],
        },
      },
    ],
    "result": [],
    "message": "질문을 처리했습니다.",
    "executionSummary": {"total": 2, "succeeded": 2, "failed": 0},
  }

  ensure_initialized()
  with SessionLocal() as session:
    ui_payload = build_chatbot_ui_payload(session, response)

  assert [action["id"] for action in ui_payload["uiActions"]] == ["focus_map:complex:1002"]
  assert ui_payload["uiActions"][0]["source"] == "simple_lookup.location"


def test_max_artifact_count_is_three():
  response = {
    "success": True,
    "status": "success",
    "question": "비교하고 추천해줘",
    "fragments": [],
    "result": [
      {
        "handler": "comparison",
        "success": True,
        "results": [
          {
            "complexId": 1002,
            "complexName": "잠실엘스",
            "latitude": 37.5124,
            "longitude": 127.0821,
            "latestDealAmount": 330000,
          },
          {
            "complexId": 1001,
            "complexName": "래미안대치팰리스",
            "latitude": 37.4988,
            "longitude": 127.0652,
            "latestDealAmount": 435000,
          },
        ],
      },
      trend_result("잠실엘스"),
      trend_result("래미안대치팰리스"),
      {
        "handler": "recommendation",
        "success": True,
        "results": [recommendation_item(1002, "잠실엘스", 37.5124, 127.0821, "31.0억원")],
      },
    ],
    "message": "질문을 처리했습니다.",
    "executionSummary": {"total": 4, "succeeded": 4, "failed": 0},
  }

  ensure_initialized()
  with SessionLocal() as session:
    ui_payload = build_chatbot_ui_payload(session, response)

  assert [artifact["type"] for artifact in ui_payload["uiArtifacts"]] == [
    "comparison_bar_chart",
    "trend_line_chart",
    "trend_line_chart",
  ]


def recommendation_item(
  complex_id: int,
  name: str,
  latitude: float,
  longitude: float,
  price_text: str,
) -> dict:
  return {
    "complexId": complex_id,
    "complexName": name,
    "parcelId": 9000000 + complex_id,
    "latitude": latitude,
    "longitude": longitude,
    "latestDealAmountText": price_text,
    "unitCnt": 500,
    "useDate": "2020-01-01",
    "infrastructure": {
      "nearestStation": {
        "name": "테스트역",
        "distanceM": 350,
      }
    },
  }


def trend_result(target_name: str) -> dict:
  return {
    "handler": "price_trend",
    "success": True,
    "observation_type": "timeseries",
    "criteria": {
      "target_type": "complex",
      "target_name": target_name,
    },
    "rows": [
      {"period_start": "2025-01-01", "avg_deal_amount": 100000, "trade_count": 1},
      {"period_start": "2025-02-01", "avg_deal_amount": 110000, "trade_count": 2},
    ],
  }
