# 강남 3구 실거래가 Server

FastAPI 기반 public read API다. v1은 `web` 프론트가 호출하는 조회 endpoint만 제공하며 RTMS 수집, raw ingest, admin 기능은 포함하지 않는다.

## 구조

- `app/main.py`: FastAPI app 생성과 router composition만 담당
- `app/health.py`: 운영 확인용 `GET /health` 단일 router
- `app/models.py`: SQLAlchemy ORM model
- `app/database.py`: SQLAlchemy engine/session, local seed bootstrap
- `app/repository.py`: 기존 import 호환용 legacy shim
- `app/chatbot/`: 자연어 질문을 intent 단위로 분해, 분류, 실행, 병합하는 orchestration 계층
- `app/real_estate/`: 부동산 조회/계산 도메인. controller/service/dto/dao/support로 분리
- `db/init/`: PostgreSQL 컨테이너 최초 생성 시 실행되는 schema/seed SQL
- `db/import/`: 나중에 큰 SQL 파일을 둘 위치
- `scripts/import-sql.sh`: SQL 또는 SQL gzip 파일을 PostgreSQL 컨테이너에 적용하는 스크립트

주요 server tree:

```text
app/
  main.py
  database.py
  models.py
  repository.py
  health.py

  chatbot/
    controller/
      router.py
      chatbot_controller.py
      intent_query_controller.py
    dto/
      chatbot_dto.py
      intent_query_dto.py
    service/
      chatbot_service.py
      classifier.py
      splitter.py
      dispatcher.py
      handler.py
      registry.py
    features/
      simple_lookup/
        slots.py
        dto.py
        policy.py
        dao.py
        service.py
      recommendation/
        slots.py
        service.py
      comparison/
        slots.py
        service.py
      price_trend/
        slots.py
        dto.py
        policy.py
        dao.py
        service.py
      legal_contract/
        slots.py
        service.py
        rag/
          controller/
            router.py
            ingestion_controller.py
            indexing_controller.py
            query_controller.py
          dto/
            ingestion.py
            indexing.py
            query.py
          service/
            ingestion_service.py
            indexing_service.py
            query_service.py
          dao/
            ingestion_dao.py
            indexing_dao.py
            query_dao.py
          parser/
            law_parser.py
            term_mapping_parser.py
          client/
            law_api_client.py
            openai_embedding_client.py
          model/
            entities.py
      unsupported/
        slots.py
        service.py
    embedding/

  real_estate/
    controller/
      router.py
      map_controller.py
      search_controller.py
      region_controller.py
      complex_controller.py
      trade_controller.py
    dto/
      map_dto.py
      search_dto.py
      region_dto.py
      complex_dto.py
      trade_dto.py
    service/
      map_service.py
      search_service.py
      region_service.py
      complex_service.py
      trade_service.py
      lookup_service.py
      recommendation_service.py
      comparison_service.py
      trend_service.py
    dao/
      region_dao.py
      complex_dao.py
      trade_dao.py
      poi_dao.py
    support/
      formatting.py
      filters.py
      poi.py
```

의존 방향은 controller -> service -> dao/support다. controller는 FastAPI parsing, `Depends(get_session)`, HTTP 404 변환만 담당하고, service는 use case 조회/계산, dao는 SQLAlchemy DB 접근, support는 포맷팅/필터/거리 계산 같은 순수 helper를 담당한다.

챗봇 intent flow:

```text
question -> split -> classify -> registry -> slots -> service -> fragment -> merge
```

`chatbot.service.registry`는 모든 `Intent`를 `FeatureSpec(intent, slot_extractor, service, default_status)`로 등록한다. `chatbot.service.handler.GenericIntentHandler` 하나가 슬롯 추출과 feature service 실행을 공통 처리한다. `recommendation`/`comparison`은 `real_estate.service.*`를 호출하고, `legal_contract`는 feature 내부 `rag` 검색 엔진을 호출한다. `/api/laws/*` 검증 endpoint는 `chatbot/features/legal_contract/rag/controller`에 남아 있으며 chatbot router에서 include한다.

## 로컬 단독 실행

`DATABASE_URL`이 없으면 in-memory SQLite를 사용하고 앱 시작 시 sample seed를 자동 적재한다.

프로젝트 메타데이터 기반 설치:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[test]"
uvicorn app.main:app --reload --port 8080
```

단순 실행 환경이나 CI에서 `requirements.txt`만 사용하는 경우:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

`requirements.txt`에는 현재 public read API 의존성과 docs에 계획된 후속 작업 의존성을 함께 둔다. 포함 범위는 레거시 스냅샷 적재/검증, BGE-M3 임베딩 기반 질의 분류, 유사도/kNN 평가, pgvector 기반 문서 검색, 법률/계약 RAG, LLM 기반 질문 분해/병합 실험이다.

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
