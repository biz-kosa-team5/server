# 강남 3구 실거래가 Server

FastAPI 기반 public read API다. v1은 `web` 프론트가 호출하는 조회 endpoint만 제공하며 RTMS 수집, raw ingest, admin 기능은 포함하지 않는다.

## 구조

- `app/main.py`: FastAPI endpoint
- `app/models.py`: SQLAlchemy ORM model
- `app/database.py`: SQLAlchemy engine/session, local seed bootstrap
- `app/repository.py`: public read query
- `db/init/`: PostgreSQL 컨테이너 최초 생성 시 실행되는 schema/seed SQL
- `db/import/`: 나중에 큰 SQL 파일을 둘 위치
- `scripts/import-sql.sh`: SQL 또는 SQL gzip 파일을 PostgreSQL 컨테이너에 적용하는 스크립트
- `scripts/build-pois-csv.py`: 지하철/교육시설 원본 CSV를 `db/import/pois.csv` 형식으로 변환하는 스크립트

## 로컬 단독 실행

`DATABASE_URL`이 없으면 in-memory SQLite를 사용하고 앱 시작 시 sample seed를 자동 적재한다.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[test]"
uvicorn app.main:app --reload --port 8080
```

## PostgreSQL 실행

```bash
docker compose up -d postgres
```

컨테이너 최초 생성 시 `db/init/01_schema.sql`, `db/init/02_seed.sql`이 자동 실행된다. 이미 volume이 만들어진 뒤 init SQL을 다시 적용하려면 volume을 지우고 재생성하거나 import script를 사용한다.

```bash
cp .env.example .env
export DATABASE_URL=postgresql+psycopg://home_search:home_search@127.0.0.1:55432/home_search
uvicorn app.main:app --reload --port 8080
```

## SQL 데이터 적재

작은 SQL 파일:

```bash
scripts/import-sql.sh db/import/gangnam_snapshot.sql
```

압축된 큰 SQL 파일:

```bash
scripts/import-sql.sh db/import/gangnam_snapshot.sql.gz
```

큰 데이터는 가능한 한 `INSERT` 다량 반복보다 PostgreSQL `COPY` 형식이나 transaction 단위 SQL로 만드는 것을 권장한다. 스크립트는 `ON_ERROR_STOP=1`로 실행되어 중간 실패 시 즉시 종료한다.

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
- 역/교육시설 좌표는 `pois` 테이블에 `category`, `name`, `subtype`, `latitude`, `longitude`만 저장한다.
- `pois.category`는 `station` 또는 `education`이며, `subtype`은 역의 호선명 또는 교육시설 유형을 저장한다.
- `pois` 데이터는 Excel 호환을 위해 UTF-8 BOM으로 저장한 `db/import/pois.csv`에서 적재한다.
