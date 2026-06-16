# 강남 3구 실거래가 Server

FastAPI 기반 public read API다. v1은 `web` 프론트가 호출하는 조회 endpoint만 제공하며 RTMS 수집, raw ingest, admin 기능은 포함하지 않는다.

## 실행

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[test]"
uvicorn app.main:app --reload --port 8080
```

## 검증

```bash
pytest
```

## 포함 API

- `GET /health`
- `POST /api/v1/map/regions`
- `POST /api/v1/map/complexes`
- `GET /api/v1/search/complexes/suggestions?q=`
- `GET /api/v1/search/complexes?q=`
- `GET /api/v1/region`
- `GET /api/v1/region/{regionId}`
- `GET /api/v1/region/{regionId}/complexes?limit=&offset=`
- `GET /api/v1/detail/{parcelId}?complexId=`
- `GET /api/v1/detail/{parcelId}/complexes`
- `GET /api/v1/trade/{parcelId}?complexId=&page=&size=`
- `GET /api/v1/trade/{parcelId}/trend?complexId=`
- `GET /api/v1/complex/{complexId}`
- `GET /api/v1/complex/{complexId}/trades?page=&size=`
- `GET /api/v1/complex/{complexId}/trade-trend`

## 데이터 정책

- `parcel` 테이블은 만들지 않는다.
- 프론트 호환용 `parcelId`는 `complexes.parcel_id`로 제공한다.
- 지도 마커는 `complexes.latitude`, `complexes.longitude`를 사용한다.
- 좌표 없는 단지는 지도 마커에서 제외하고 검색/상세에서는 반환한다.
