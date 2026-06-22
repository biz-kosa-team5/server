"""H1 단순조회 핸들러의 입력과 출력 DTO.

이 파일의 모델은 자연어를 해석하거나 DB를 조회하지 않는다. 상위
에이전트, H1 서비스, 최종 응답 생성 계층이 같은 데이터 구조를 사용하게
만드는 것이 목적이다.

입력값 사이의 정책 검증(예: area와 pyeong의 동시 입력 금지,
start_date가 end_date보다 늦은지 여부)은 다음 차수에서 Policy 계층이
담당한다. DTO는 우선 전달받은 데이터의 기본 타입과 필드 이름을 고정한다.

정상 조회 결과는 위치와 거래라는 두 가지 기본 형식으로 나눈다. 각 형식을
DTO로 정의하면 필수 필드 누락이나 오타를 Pydantic이 바로 발견할 수 있다.
최상위 `data`는 조회 유형과 관계없이 항상 리스트로 반환한다.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SimpleLookupQueryType(StrEnum):
  """H1이 지원하는 조회 유형.

  query_type은 상위 에이전트와 H1 사이의 호출 계약이므로 Enum으로 제한한다.
  허용되지 않은 값은 SimpleLookupSlots 생성 단계에서 ValidationError가 된다.
  """

  LOCATION = "location"
  TRADE_HISTORY = "trade_history"
  RECORD_HIGH = "record_high"


class SimpleLookupBaseModel(BaseModel):
  """H1 DTO가 공통으로 사용하는 Pydantic 설정.

  `extra="forbid"`는 정의되지 않은 슬롯이 조용히 무시되는 일을 막는다.
  슬롯 이름의 오타나 상위 에이전트와 H1 사이의 계약 불일치를 요청
  초기에 발견하기 위한 설정이다.

  `use_enum_values=True`를 사용하므로 JSON으로 변환할 때 Enum 객체 대신
  API 계약에 정의된 문자열(`location`, `no_result` 등)이 출력된다.
  """

  model_config = ConfigDict(extra="forbid", use_enum_values=True)


class SimpleLookupSlots(SimpleLookupBaseModel):
  """상위 에이전트가 H1에 전달하는 입력 슬롯.

  모든 조건 슬롯을 선택값으로 둔 이유는 조회 유형마다 필요한 필드가
  다르기 때문이다. 예를 들어 location은 면적과 기간이 필요하지 않지만,
  trade_history는 해당 조건들을 선택적으로 사용할 수 있다.

  필수값 누락이나 서로 충돌하는 슬롯의 판정은 Policy 계층에서 수행해
  `SimpleLookupResult` 형태의 업무 실패로 반환한다.
  """

  # 원질문은 로그와 추적을 위한 메타데이터다. H1이 이 문장을 다시
  # 해석해 query_type이나 limit을 임의로 변경해서는 안 된다.
  original_question: str | None = Field(
    default=None,
    description="상위 에이전트가 받은 원질문. H1 조회 판단에는 사용하지 않는다.",
  )

  # 어떤 조회를 실행할지는 상위 에이전트가 결정해서 전달한다.
  query_type: SimpleLookupQueryType = Field(description="H1에서 실행할 조회 유형")

  # H1은 단지 한 곳만 다룬다. 검색 결과가 여러 곳이면 임의로 고르지
  # 않고 ambiguous_target과 후보 목록을 반환한다.
  complex_name: str | None = Field(default=None, description="조회 대상 아파트 단지명")

  # 전용면적(㎡) 조건이다. area는 단일 면적, min/max는 범위 요청에 쓴다.
  area: float | None = Field(default=None, description="사용자가 지정한 단일 전용면적(㎡)")
  area_min: float | None = Field(default=None, description="전용면적 하한(㎡)")
  area_max: float | None = Field(default=None, description="전용면적 상한(㎡)")

  # 사용자가 시장에서 통용되는 평형으로 질문했을 때 받는 슬롯이다.
  # 실제 전용면적으로 연결하는 계산과 후보 선택은 Policy에서 수행한다.
  pyeong: float | None = Field(default=None, description="사용자가 지정한 단일 평형")
  pyeong_min: float | None = Field(default=None, description="평형 범위의 하한")
  pyeong_max: float | None = Field(default=None, description="평형 범위의 상한")

  # period는 2m(2개월), 2y(2년)처럼 "양의 정수 + m/y" 형식의
  # 상대 기간 표현이다.
  # 날짜 문자열은 외부 계약을 단순하게 유지하기 위해 이 DTO에서는
  # 문자열로 받고, Policy에서 datetime.date로 변환하고 검증한다.
  period: str | None = Field(default=None, description="상대 조회 기간")
  start_date: str | None = Field(default=None, description="조회 시작일(YYYY-MM-DD)")
  end_date: str | None = Field(default=None, description="조회 종료일(YYYY-MM-DD)")

  # trade_history에서는 조회 건수로 사용한다. record_high는 원칙적으로
  # 한 건만 반환하므로 허용 여부를 Policy에서 별도로 판단한다.
  limit: int | None = Field(default=None, description="반환할 최대 거래 건수")

  @field_validator(
    "area",
    "area_min",
    "area_max",
    "pyeong",
    "pyeong_min",
    "pyeong_max",
    "limit",
    mode="before",
  )
  @classmethod
  def reject_boolean_number(cls, value):
    """숫자 슬롯에 전달된 boolean을 숫자로 자동 변환하기 전에 차단한다.

    Python과 Pydantic은 기본적으로 True를 1, False를 0으로 변환할 수 있다.
    그러면 `area=true`가 1㎡ 조건으로 처리되는 등 호출 오류가 숨어버리므로
    원본 입력을 확인할 수 있는 before validator에서 명시적으로 거부한다.
    """

    if isinstance(value, bool):
      raise ValueError("숫자 슬롯에 boolean 값을 사용할 수 없습니다.")
    return value


class LocationData(SimpleLookupBaseModel):
  """location 조회 결과 한 건의 형식.

  위치 조회도 `SimpleLookupResult.data` 안에 한 개짜리 리스트로 담긴다.
  공통 DB에서 주소나 좌표가 비어 있을 수 있으므로 해당 필드는 선택값으로
  둔다. 주소가 있고 좌표만 없는 경우도 정상적인 위치 결과가 될 수 있다.
  """

  complex_id: int
  complex_name: str
  trade_name: str | None = None
  address: str | None = None
  latitude: float | None = None
  longitude: float | None = None


class TradeData(SimpleLookupBaseModel):
  """실거래 조회 결과 한 건의 형식.

  trade_history는 이 객체를 여러 개 반환하고, record_high는 이 객체를
  한 개만 반환한다. 두 조회 모두 최상위에서는 리스트 형태를 사용한다.
  """

  trade_id: int
  deal_date: str = Field(description="거래일(YYYY-MM-DD)")

  # 공통 DB의 deal_amount는 만 원 단위다. 숫자만 전달하면 호출 계층이
  # 원이나 억 단위로 오해할 수 있으므로 단위를 결과에 함께 포함한다.
  deal_amount: int = Field(description="거래금액(만원)")
  deal_amount_unit: str = Field(default="만원", description="거래금액 단위")

  exclusive_area: float = Field(description="전용면적(㎡)")
  floor: int | None = None
  apt_dong: str | None = None


# H1의 정상 조회 결과 한 건은 위치 정보 또는 거래 정보 중 하나다.
SimpleLookupData = LocationData | TradeData


class SimpleLookupResult(SimpleLookupBaseModel):
  """H1이 상위 에이전트에 반환하는 공통 결과.

  성공과 업무상 실패를 하나의 구조로 반환하면 호출 계층은 예외마다
  서로 다른 형태를 처리할 필요가 없다. 실제 사용 규칙은 다음과 같다.

  - location: LocationData 한 개를 리스트에 담아 반환
  - trade_history: TradeData 여러 개를 리스트로 반환
  - record_high: TradeData 한 개를 리스트에 담아 반환
  - 실패: 빈 리스트를 반환하고 reason에 실패 사유를 기록

  이 상호 관계의 강제 검증은 서비스 구현 방식과 함께 다음 단계에서
  확정한다. 지금은 각 계층이 공유할 필드 계약을 먼저 제공한다.
  """

  success: bool
  query_type: SimpleLookupQueryType

  # 조회 결과는 항상 리스트로 통일한다. 이 덕분에 상위 에이전트는
  # 단건/복수 건을 구분해 자료형을 바꾸지 않고 같은 방식으로 순회할 수 있다.
  #
  # location      → [LocationData]
  # trade_history → [TradeData, TradeData, ...]
  # record_high   → [TradeData]
  # 실패          → []
  data: list[SimpleLookupData] = Field(default_factory=list)

  # Policy가 정규화한 뒤 실제 조회에 적용한 조건이다. 테스트와 장애
  # 분석에서 어떤 조건으로 조회했는지 확인할 수 있도록 항상 남긴다.
  criteria: dict[str, Any] = Field(default_factory=dict)

  # 실패 응답에서 사용하는 필드다. 성공 응답에서는 둘 다 None이다.
  reason: str | None = None
  message: str | None = None

  # 동일한 이름의 단지가 여러 개라 ambiguous_target이 발생했을 때
  # 상위 에이전트가 사용자에게 보여줄 단지 후보를 담는다.
  candidates: list[dict[str, Any]] = Field(default_factory=list)

  # 해당 query_type에서 사용하지 않은 정상 슬롯을 기록한다. mutable
  # 기본값을 공유하지 않도록 default_factory를 사용한다.
  ignored_slots: dict[str, Any] = Field(default_factory=dict)
