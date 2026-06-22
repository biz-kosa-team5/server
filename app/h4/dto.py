"""H4 시세추이·시계열 조회의 입력과 출력 DTO.

이 파일은 상위 에이전트가 H4에 전달하는 슬롯과 H4가 반환하는 결과의
형식을 정의한다. 자연어를 다시 해석하거나 기간·면적을 계산하거나 DB를
조회하는 기능은 포함하지 않는다.

역할을 나누면 다음과 같다.

- DTO: 전달받을 수 있는 필드와 각 필드의 기본 자료형을 고정
- Policy: query_type별 필수값, 슬롯 충돌, 기간·면적 등을 검증하고 정규화
- DAO: Policy가 만든 조회 조건으로 DB를 조회
- Service: 전체 흐름을 연결하고 TrendResult를 생성

정상 조회 결과는 시계열 지점, 가격 변화율 순위, 실거래가 순위라는 세
형식으로 나뉜다. 최상위 ``data``는 H1과 마찬가지로 항상 리스트를
사용하므로 상위 에이전트가 조회 유형마다 자료형을 다르게 처리하지 않아도
된다.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TrendQueryType(StrEnum):
  """H4가 지원하는 네 가지 조회 유형.

  query_type은 상위 에이전트가 어떤 H4 기능을 호출할지 지정하는 값이다.
  Enum에 없는 문자열은 DTO 생성 시점에 ValidationError가 발생한다.
  """

  COMPLEX_TREND = "complex_trend"  # 특정 아파트 단지의 기간별 가격 흐름 조회
  REGION_TREND = "region_trend"  # 특정 지역에 포함된 아파트의 기간별 가격 흐름 조회
  PRICE_CHANGE_RANKING = "price_change_ranking"  # 지역 내 단지별 가격 상승률·하락률 순위 조회
  PRICE_RANKING = "price_ranking"  # 지역 내 단지별 최고가·최저가 실거래 순위 조회


class TrendBaseModel(BaseModel):
  """모든 H4 DTO가 공통으로 사용하는 Pydantic 설정.

  ``extra="forbid"``는 정의하지 않은 슬롯이나 필드명의 오타를 조용히
  무시하지 않고 즉시 발견하게 한다.

  ``use_enum_values=True``를 사용하므로 모델과 JSON 결과에서는 Enum 객체
  대신 ``complex_trend`` 같은 약속된 문자열이 사용된다.
  """

  model_config = ConfigDict(extra="forbid", use_enum_values=True)


class TrendSlots(TrendBaseModel):
  """상위 에이전트가 H4에 전달하는 입력 슬롯.

  query_type을 제외한 슬롯이 모두 선택값인 이유는 조회 종류마다 필요한
  조건이 다르기 때문이다. 예를 들어 complex_trend에는 complex_name이
  필요하지만 price_ranking에는 지역 정보가 필요하다.

  이 DTO에서는 우선 필드명과 자료형만 검사한다. 다음과 같은 업무 규칙은
  2단계에서 구현할 Policy가 담당한다.

  - query_type별 필수 슬롯 확인
  - complex_name과 region_name의 동시 입력 금지
  - area 조건과 pyeong 조건의 동시 입력 금지
  - period와 직접 날짜 범위의 동시 입력 금지
  - 날짜 순서, 기간 한도, interval 및 limit 검증
  """

  # 원질문은 로그와 결과 추적을 위한 메타데이터다. H4가 이 문장을 다시
  # 분석해 query_type이나 조건을 임의로 바꾸지는 않는다.
  original_question: str | None = Field(
    default=None,
    description="상위 에이전트가 받은 원질문. H4의 조건 판단에는 사용하지 않는다.",
  )

  # 실행할 기능은 상위 에이전트가 선택해서 전달한다.
  query_type: TrendQueryType = Field(description="H4에서 실행할 조회 유형")

  # 특정 단지의 시계열을 조회할 때 사용한다. 동명 단지 확정은 Service가
  # DAO 검색 결과를 이용해 수행한다.
  complex_name: str | None = Field(default=None, description="조회 대상 아파트 단지명")

  # 한 지역을 조회할 때는 region_name을 사용한다.
  region_name: str | None = Field(default=None, description="조회 대상 단일 지역명")

  # '강남 3구'처럼 상위 에이전트가 하나의 표현을 여러 실제 지역으로
  # 풀어낸 경우에는 region_names를 사용한다.
  region_names: list[str] | None = Field(
    default=None,
    description="함께 조회할 복수 지역명",
  )

  # 전용면적(㎡) 조건이다. area는 단일 면적, min/max는 범위 요청에 쓴다.
  # 단일 면적의 허용 오차 적용은 DTO가 아니라 Policy의 역할이다.
  area: float | None = Field(default=None, description="사용자가 지정한 단일 전용면적(㎡)")
  area_min: float | None = Field(default=None, description="전용면적 하한(㎡)")
  area_max: float | None = Field(default=None, description="전용면적 상한(㎡)")

  # 사용자가 '34평', '30평대'처럼 질문했을 때 상위 에이전트가 전달하는
  # 슬롯이다. 실제 전용면적 범위로 변환하는 계산은 Policy에서 수행한다.
  pyeong: float | None = Field(default=None, description="사용자가 지정한 단일 평형")
  pyeong_min: float | None = Field(default=None, description="평형 범위의 하한")
  pyeong_max: float | None = Field(default=None, description="평형 범위의 상한")

  # period는 2m, 3y 같은 상대 기간이다. 날짜 문자열은 외부 호출 계약을
  # 단순하게 유지하기 위해 문자열로 받고 Policy에서 date로 변환한다.
  period: str | None = Field(default=None, description="상대 조회 기간(예: 6m, 3y)")
  start_date: str | None = Field(default=None, description="조회 시작일(YYYY-MM-DD)")
  end_date: str | None = Field(default=None, description="조회 종료일(YYYY-MM-DD)")

  # 시계열을 월·분기·연 단위 중 어떤 간격으로 묶을지 지정한다. 값이
  # 없으면 전체 조회 기간에 따라 Policy가 적절한 간격을 선택한다.
  interval: str | None = Field(
    default=None,
    description="시계열 집계 간격(month, quarter, year)",
  )

  # 변화율 순위에서 상승/하락 방향을 지정한다.
  change_direction: str | None = Field(
    default=None,
    description="가격 변화율 순위 방향(up, down)",
  )

  # 실거래가 순위에서 고가/저가 정렬 방향을 지정한다.
  rank_order: str | None = Field(
    default=None,
    description="실거래가 순위 정렬 방향(highest, lowest)",
  )

  # 순위 조회가 최대 몇 개의 단지를 반환할지 지정한다.
  limit: int | None = Field(default=None, description="반환할 최대 순위 개수")

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
    """숫자 슬롯에 들어온 boolean을 숫자로 자동 변환하기 전에 거부한다.

    Python에서 True와 False는 각각 1과 0처럼 취급될 수 있다. 이를
    허용하면 ``limit=true``가 ``limit=1``로 처리되는 호출 오류가 숨어
    버리므로 원본 값을 확인할 수 있는 before validator에서 차단한다.
    """

    if isinstance(value, bool):
      raise ValueError("숫자 슬롯에 boolean 값을 사용할 수 없습니다.")
    return value


class TrendPoint(TrendBaseModel):
  """단지 또는 지역 시계열의 한 기간 구간에 해당하는 결과.

  complex_trend와 region_trend는 이 객체를 시간순으로 여러 개 반환한다.
  금액 관련 값은 공통 DB의 저장 단위에 맞춰 모두 만 원을 기준으로 한다.
  """

  period_start: str = Field(description="집계 구간 시작일(YYYY-MM-DD)")
  avg_deal_amount: float = Field(description="평균 거래금액(만원)")
  avg_price_per_sqm: float = Field(description="평균 ㎡당 거래가격(만원/㎡)")
  min_deal_amount: int = Field(description="구간 내 최저 거래금액(만원)")
  max_deal_amount: int = Field(description="구간 내 최고 거래금액(만원)")
  trade_count: int = Field(description="구간에 포함된 거래 건수")
  avg_exclusive_area: float = Field(description="평균 전용면적(㎡)")

  # 단위를 결과에 명시해 상위 에이전트가 원·만원·억원을 혼동하지 않게 한다.
  deal_amount_unit: str = Field(default="만원", description="거래금액 단위")
  price_per_sqm_unit: str = Field(default="만원/㎡", description="㎡당 가격 단위")


class PriceChangeRankingItem(TrendBaseModel):
  """지역 내 단지별 가격 변화율 순위 한 건.

  서로 다른 면적의 거래금액을 직접 비교하지 않도록 시작·종료 가격은
  ㎡당 가격을 사용한다. 시작 및 종료 구간의 거래 건수도 함께 반환해
  상위 계층이 변화율의 데이터 충분성을 확인할 수 있게 한다.
  """

  rank: int
  complex_id: int
  complex_name: str
  address: str | None = None
  start_avg_price_per_sqm: float = Field(description="시작 구간 평균 ㎡당 가격(만원/㎡)")
  end_avg_price_per_sqm: float = Field(description="종료 구간 평균 ㎡당 가격(만원/㎡)")
  change_amount: float = Field(description="㎡당 가격 증감액(만원/㎡)")
  change_rate: float = Field(description="가격 변화율(%)")
  start_trade_count: int = Field(description="시작 비교 구간 거래 건수")
  end_trade_count: int = Field(description="종료 비교 구간 거래 건수")
  avg_exclusive_area: float = Field(description="비교 대상 거래의 평균 전용면적(㎡)")
  price_per_sqm_unit: str = Field(default="만원/㎡", description="㎡당 가격 단위")


class PriceRankingItem(TrendBaseModel):
  """지역 내 단지별 최고가 또는 최저가 순위 한 건.

  같은 단지가 순위에 여러 번 나타나지 않도록 DAO는 조회 기간 안에서
  단지별 대표 거래 한 건을 고른 뒤 순위를 계산한다.
  """

  rank: int
  complex_id: int
  complex_name: str
  address: str | None = None
  trade_id: int
  deal_date: str = Field(description="거래일(YYYY-MM-DD)")
  deal_amount: int = Field(description="거래금액(만원)")
  deal_amount_unit: str = Field(default="만원", description="거래금액 단위")
  exclusive_area: float = Field(description="전용면적(㎡)")
  floor: int | None = None
  apt_dong: str | None = None


# H4의 정상 결과 한 건은 아래 세 종류 중 하나다.
TrendData = TrendPoint | PriceChangeRankingItem | PriceRankingItem


class TrendResult(TrendBaseModel):
  """H4가 상위 에이전트에 반환하는 공통 결과.

  조회 유형이 달라도 최상위 구조는 하나로 통일한다.

  - complex_trend / region_trend: TrendPoint 여러 개
  - price_change_ranking: PriceChangeRankingItem 여러 개
  - price_ranking: PriceRankingItem 여러 개
  - 업무상 실패: 빈 리스트와 reason, message

  아직 1단계이므로 query_type과 data 종류의 세부 조합은 강제하지 않는다.
  실제 조회 흐름이 구현되는 Service 단계에서 올바른 결과 DTO를 생성한다.
  """

  success: bool
  query_type: TrendQueryType
  data: list[TrendData] = Field(default_factory=list)

  # Policy가 정규화하고 실제 DB 조회에 사용한 조건을 남긴다.
  criteria: dict[str, Any] = Field(default_factory=dict)

  # 시계열의 전체 변화율이나 순위 기준처럼 결과 전체에 관한 요약값이다.
  # 요약 문장 생성은 상위 에이전트의 역할이므로 H4에서는 계산값만 담는다.
  summary: dict[str, Any] | None = None

  # 업무상 실패 시 사용한다. 성공 결과에서는 두 값이 모두 None이다.
  reason: str | None = None
  message: str | None = None

  # 단지명 또는 지역명이 여러 후보와 일치한 경우 사용자에게 선택지를
  # 보여주기 위한 목록이다.
  candidates: list[dict[str, Any]] = Field(default_factory=list)

  # 해당 query_type에서 사용하지 않은 정상 슬롯을 기록한다.
  ignored_slots: dict[str, Any] = Field(default_factory=dict)
