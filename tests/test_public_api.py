from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
  response = client.get("/health")

  assert response.status_code == 200
  assert response.json() == {"status": "ok"}


def test_map_region_markers_are_arrays():
  response = client.post(
    "/api/v1/map/regions",
    json={"swLat": 37.4, "swLng": 126.9, "neLat": 37.6, "neLng": 127.2, "region": "si-gun-gu"},
  )

  assert response.status_code == 200
  payload = response.json()
  assert isinstance(payload, list)
  assert {item["name"] for item in payload} == {"강남구", "서초구", "송파구"}


def test_map_complex_markers_exclude_complex_without_coordinates():
  response = client.post(
    "/api/v1/map/complexes",
    json={"swLat": 37.4, "swLng": 126.9, "neLat": 37.6, "neLng": 127.2},
  )

  assert response.status_code == 200
  payload = response.json()
  names = {item["name"] for item in payload}
  assert "래미안대치팰리스" in names
  assert "좌표없는강남단지" not in names
  assert all(item["lat"] is not None and item["lng"] is not None for item in payload)


def test_search_returns_complex_without_coordinates():
  response = client.get("/api/v1/search/complexes", params={"q": "좌표없는"})

  assert response.status_code == 200
  assert response.json() == [
    {
      "complexId": 1005,
      "complexName": "좌표없는강남단지",
      "parcelId": 9001003,
      "latitude": None,
      "longitude": None,
      "address": "서울특별시 강남구 개포동",
    }
  ]


def test_suggestions_shape():
  response = client.get("/api/v1/search/complexes/suggestions", params={"q": "래미안"})

  assert response.status_code == 200
  assert response.json()[0] == {
    "complexId": 1001,
    "complexName": "래미안대치팰리스",
    "parcelId": 9001001,
    "address": "서울특별시 강남구 대치동 633",
  }


def test_region_complexes_support_limit_offset():
  response = client.get("/api/v1/region/11680/complexes", params={"limit": 1, "offset": 1})

  assert response.status_code == 200
  payload = response.json()
  assert len(payload) == 1
  assert {"complexId", "complexName", "parcelId", "latitude", "longitude"}.issubset(payload[0])


def test_detail_by_parcel_and_complex_id():
  response = client.get("/api/v1/detail/9001001", params={"complexId": 1001})

  assert response.status_code == 200
  payload = response.json()
  assert payload["parcelId"] == 9001001
  assert payload["complexId"] == 1001
  assert payload["name"] == "래미안대치팰리스"
  assert payload["platArea"] is None


def test_trade_pagination_shape():
  response = client.get("/api/v1/trade/9001001", params={"complexId": 1001, "page": 0, "size": 2})

  assert response.status_code == 200
  payload = response.json()
  assert payload["parcelId"] == 9001001
  assert payload["complexId"] == 1001
  assert payload["page"] == 0
  assert payload["size"] == 2
  assert payload["totalElements"] == 3
  assert payload["totalPages"] == 2
  assert [trade["tradeId"] for trade in payload["content"]] == [5003, 5002]


def test_trend_aggregates_by_month():
  response = client.get("/api/v1/trade/9001001/trend", params={"complexId": 1001})

  assert response.status_code == 200
  assert response.json() == [
    {"month": "2025-12", "avgAmount": 405000.0, "count": 1, "minAmount": 405000, "maxAmount": 405000},
    {"month": "2026-01", "avgAmount": 427500.0, "count": 2, "minAmount": 420000, "maxAmount": 435000},
  ]


def test_complex_id_routes():
  detail = client.get("/api/v1/complex/1003")
  trades = client.get("/api/v1/complex/1003/trades", params={"page": 0, "size": 10})
  trend = client.get("/api/v1/complex/1003/trade-trend")

  assert detail.status_code == 200
  assert trades.status_code == 200
  assert trend.status_code == 200
  assert detail.json()["parcelId"] == 9002001
  assert trades.json()["totalElements"] == 2
  assert [point["month"] for point in trend.json()] == ["2026-01", "2026-03"]
