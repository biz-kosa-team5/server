# H1 단순조회 핸들러

## 역할

H1은 특정 아파트 단지 한 곳의 위치와 실거래 정보를 조회한다.

자연어 해석과 최종 답변 생성은 상위 에이전트가 담당한다. H1은 전달받은 슬롯을 검증하고 DB 조회 결과를 구조화해 반환한다.

지원하는 `query_type`:

| query_type | 처리 내용 |
|---|---|
| `location` | 단지 주소와 좌표 조회 |
| `trade_history` | 기간·면적 조건에 맞는 실거래 내역 조회 |
| `record_high` | 조건에 맞는 거래금액 최고가 1건 조회 |

H1에서 처리하지 않는 기능:

```text
조건 기반 추천
여러 단지 비교
시세 변화·상승률·지역 순위
법률·계약 관련 질문
```

---

## 파일 구성

```text
simple_lookup/
├─ dto.py       입력·출력 DTO와 query_type Enum
├─ policy.py    슬롯 검증과 조회 조건 정규화
├─ dao.py       공통 DB 조회
├─ service.py   전체 처리 흐름과 단지 확정
└─ __init__.py
```

---

## 입력 슬롯

```python
class SimpleLookupSlots:
    original_question: str | None
    query_type: SimpleLookupQueryType
    complex_name: str | None

    area: float | None
    area_min: float | None
    area_max: float | None

    pyeong: float | None
    pyeong_min: float | None
    pyeong_max: float | None

    period: str | None
    start_date: str | None
    end_date: str | None

    limit: int | None
```

입력 예시:

```json
{
  "query_type": "trade_history",
  "complex_name": "잠실엘스",
  "pyeong": 34,
  "period": "2m",
  "limit": 5
}
```

잘못된 `query_type`, 정의되지 않은 슬롯, 자료형 오류는 DTO 생성 단계에서 `ValidationError`로 처리한다.

---

## 처리 흐름

```text
SimpleLookupSlots
→ Policy 검증·정규화
→ 정확 일치/부분 일치로 단지 확정
→ 평형 입력 시 실제 전용면적 확정
→ query_type별 DAO 조회
→ LocationData 또는 TradeData 변환
→ SimpleLookupResult 반환
```

### 단지 확정

```text
정확 일치 후보 1개 → 해당 단지 사용
정확 일치 없음 → 부분 일치 검색
후보 없음 → target_not_found
후보 여러 개 → ambiguous_target와 후보 목록 반환
```

검색 시 단지명의 공백과 영문 대소문자를 무시한다.

---

## 면적 정책

### 전용면적

```text
area=84
→ 83㎡ 이상 85㎡ 이하 조회
```

`area_min`, `area_max`가 들어오면 전달된 범위를 사용한다.

### 평형

평형은 공급면적 표현으로 보고 교육용 정책으로 전용률 75%를 적용한다.

```text
예상 전용면적 = 평형 × 3.3058 × 0.75
```

단일 평형은 해당 단지의 실제 거래 면적 중 예상값과 가장 가까운 면적을 선택한다.

```text
차이 3㎡ 이내 → 선택
차이 3㎡ 초과 → unsupported_request
차이가 같으면 작은 전용면적 우선
```

평형대는 예상 전용면적 범위로 변환해 조회한다.

---

## 기간 정책

`period`는 `양의 정수 + m/y` 형식이다.

```text
2m → 2개월
8m → 8개월
2y → 2년
```

지원 범위:

```text
최대 180개월
최대 15년
```

기간 계산은 시스템 날짜가 아니라 주입된 `base_date`를 사용한다. 주입값이 없으면 날짜 조건이 있는 거래 조회에서만 DB 최신 거래일을 조회한다.

`location`은 날짜 슬롯을 조회에 사용하지 않으며, 정상 값은 `ignored_slots`에 기록한다.

---

## 반환값

모든 업무 결과는 `SimpleLookupResult`로 반환한다.

```python
class SimpleLookupResult:
    success: bool
    query_type: SimpleLookupQueryType
    data: list[LocationData | TradeData]
    criteria: dict
    reason: str | None
    message: str | None
    candidates: list[dict]
    ignored_slots: dict
```

`data`는 항상 리스트다.

```text
location      → [LocationData]
trade_history → [TradeData, ...]
record_high   → [TradeData]
실패          → []
```

거래금액은 만 원 단위이며 `deal_amount_unit="만원"`을 함께 반환한다.

---

## 실패 사유

| reason | 의미 |
|---|---|
| `invalid_request` | 슬롯 값이나 조합이 잘못됨 |
| `unsupported_request` | 유효한 요청이지만 현재 정책에서 지원하지 않음 |
| `target_not_found` | 단지를 찾지 못함 |
| `ambiguous_target` | 단지 후보가 여러 개임 |
| `no_result` | 조건에 맞는 결과가 없음 |

DB 연결 실패와 SQL 실행 오류는 업무 실패로 숨기지 않고 상위 계층으로 전달한다.

---

## 호출 예시

```python
dao = SimpleLookupDao(session)
service = SimpleLookupService(
    dao,
    base_date="2026-03-19",
)

slots = SimpleLookupSlots(
    query_type="trade_history",
    complex_name="잠실엘스",
    area=84,
    period="1y",
)

result = service.handle(slots)
```

상위 에이전트는 `result.data`와 원질문을 이용해 최종 자연어 답변을 생성한다.

---

## 테스트

H1 테스트는 다음 파일에 통합돼 있다.

```text
tests/test_simple_lookup.py
```

테스트 범위:

```text
DTO 계약
면적·평형·기간 Policy
단지 정확·부분·동명 검색
location / trade_history / record_high
업무 실패와 DB 오류 전파
```
