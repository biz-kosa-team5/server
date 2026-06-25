from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chatbot.features.simple_lookup.dto import (
    SimpleLookupCriteria,
    SimpleLookupError,
)
from app.models import Complex, Trade

# 단순조회에서 단지 확정과 실제 DB 조회를 담당하는 DAO
class SimpleLookupDao:
    def __init__(self, session: Session) -> None:
        self.session = session

    # 단지명을 확정한 뒤 주소와 좌표 정보를 반환
    def find_location(self, criteria: SimpleLookupCriteria) -> list[dict[str, Any]]:
        complex_ = self._resolve_complex(criteria.complex_name)

        if (
            complex_.address is None
            and complex_.latitude is None
            and complex_.longitude is None
        ):
            raise SimpleLookupError(
                "no_result",
                "해당 단지의 위치 정보가 없습니다.",
            )

        return [{
            "complex_id": complex_.id,
            "complex_name": complex_.name,
            "trade_name": complex_.trade_name,
            "address": complex_.address,
            "latitude": complex_.latitude,
            "longitude": complex_.longitude,
        }]

    # 단지 확정 후 조건에 맞는 실거래 내역을 조회
    def find_trades(
        self,
        criteria: SimpleLookupCriteria,
    ) -> list[dict[str, Any]]:
        complex_ = self._resolve_complex(criteria.complex_name)

        stmt = select(Trade).where(Trade.complex_id == complex_.id)
        stmt = self._apply_trade_filters(stmt, criteria)

        date_order = criteria.sort_order or "latest"
        if criteria.price_order == "highest":
            amount_direction = Trade.deal_amount.desc()
        elif criteria.price_order == "lowest":
            amount_direction = Trade.deal_amount.asc()
        else:
            amount_direction = None

        if date_order == "oldest":
            date_directions = (Trade.deal_date.asc(), Trade.id.asc())
        else:
            date_directions = (Trade.deal_date.desc(), Trade.id.desc())

        if amount_direction is not None:
            stmt = stmt.order_by(amount_direction, *date_directions)
        else:
            stmt = stmt.order_by(*date_directions)
        stmt = stmt.limit(criteria.limit)

        rows = self.session.scalars(stmt).all()

        if not rows:
            raise SimpleLookupError(
                "no_result",
                "조건에 맞는 실거래 내역을 찾지 못했습니다.",
            )

        return [self._to_trade_dict(row, complex_) for row in rows]

    # 이전 이름과의 호환을 위한 래퍼
    def find_trade_history(
        self,
        criteria: SimpleLookupCriteria,
    ) -> list[dict[str, Any]]:
        return self.find_trades(criteria)

    # 이전 이름과의 호환을 위한 래퍼
    def find_record_price(
        self,
        criteria: SimpleLookupCriteria,
    ) -> list[dict[str, Any]]:
        return self.find_trades(criteria)

    # name/trade_name 기준으로 정확 일치 우선, 이후 부분 일치로 단지 확정
    def _resolve_complex(self, complex_name: str) -> Complex:
        for name, allow_partial in _complex_name_variants(complex_name):
            pattern = f"%{name}%"
            search_steps = [
                Complex.name == name,
                Complex.trade_name == name,
            ]
            if allow_partial:
                search_steps.extend([
                    Complex.name.ilike(pattern),
                    Complex.trade_name.ilike(pattern),
                ])

            for condition in search_steps:
                candidates = self._find_complexes(condition)

                if len(candidates) == 1:
                    return candidates[0]
                if len(candidates) > 1:
                    raise self._ambiguous_error(candidates)

        raise SimpleLookupError(
            "target_not_found",
            "일치하는 아파트 단지를 찾지 못했습니다.",
        )

    # 전달받은 검색 조건으로 complexes 테이블에서 단지 후보 조회
    def _find_complexes(self, condition: Any) -> list[Complex]:
        stmt = (
            select(Complex)
            .where(condition)
            .order_by(Complex.name, Complex.id)
        )
        return list(self.session.scalars(stmt).all())
    
    # Criteria에 포함된 면적 조건과 기간 조건을 Trade 조회 쿼리에 적용
    def _apply_trade_filters(self, stmt, criteria: SimpleLookupCriteria):
        if criteria.area_min is not None:
            stmt = stmt.where(Trade.excl_area >= criteria.area_min)
        if criteria.area_max is not None:
            stmt = stmt.where(Trade.excl_area <= criteria.area_max)
        if criteria.start_date is not None:
            stmt = stmt.where(Trade.deal_date >= criteria.start_date.isoformat())
        if criteria.end_date is not None:
            stmt = stmt.where(Trade.deal_date <= criteria.end_date.isoformat())
        return stmt

    # 단지 후보가 여러 개인 경우 상위 단계에서 재질문할 수 있도록 후보 목록 생성
    @staticmethod
    def _ambiguous_error(candidates: list[Complex]) -> SimpleLookupError:
        return SimpleLookupError(
            "ambiguous_target",
            "조건에 맞는 아파트 단지가 여러 개 있습니다.",
            candidates=[
                {
                    "complex_id": row.id,
                    "complex_name": row.name,
                    "trade_name": row.trade_name,
                    "address": row.address,
                }
                for row in candidates
            ],
        )

    # Trade ORM 객체를 단순조회 응답용 dict로 변환
    @staticmethod
    def _to_trade_dict(row: Trade, complex_: Complex) -> dict[str, Any]:
        return {
            "complex_id": complex_.id,
            "complex_name": complex_.name,
            "trade_name": complex_.trade_name,
            "deal_date": row.deal_date,
            "deal_amount": row.deal_amount,
            "exclusive_area": row.excl_area,
            "floor": row.floor,
            "apt_dong": row.apt_dong,
        }


def _complex_name_variants(complex_name: str) -> list[tuple[str, bool]]:
    normalized = " ".join(complex_name.split())
    compact = normalized.replace(" ", "")
    variants = [(normalized, True)]

    if compact != normalized:
        variants.append((compact, True))

    jugong_alias = _numbered_jugong_alias(compact)
    if jugong_alias is not None:
        variants.append((jugong_alias, True))

    for suffix in ("아파트",):
        if compact.endswith(suffix) and len(compact) > len(suffix):
            variants.append((compact[: -len(suffix)], False))

    deduped: list[tuple[str, bool]] = []
    seen: set[str] = set()
    for value, allow_partial in variants:
        if value and value not in seen:
            deduped.append((value, allow_partial))
            seen.add(value)
    return deduped


def _numbered_jugong_alias(complex_name: str) -> str | None:
    matched = re.fullmatch(r"(?P<prefix>.+?)(?P<number>\d+)단지", complex_name)
    if matched is None or "주공" in complex_name:
        return None

    return f"{matched.group('prefix')}주공{matched.group('number')}단지"
