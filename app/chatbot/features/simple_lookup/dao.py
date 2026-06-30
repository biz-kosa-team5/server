"""simple_lookup DAO."""

from __future__ import annotations

import re
from typing import Any, Mapping

from sqlalchemy import func, select, text, Date, cast
from sqlalchemy.orm import Session
from app.models import Complex, Region, Trade

from app.chatbot.features.simple_lookup.dto import (
    PRICE_LOWEST,
    SORT_OLDEST,
    SimpleLookupCriteria,
    SimpleLookupError,
)


class SimpleLookupDao:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _dialect_name(self) -> str:
        bind = self.session.get_bind()
        return bind.dialect.name if bind is not None else ""

    def _deal_date_order_expression(self) -> Any:
        if self._dialect_name() == "sqlite":
            return Trade.deal_date
        return cast(Trade.deal_date, Date)

    def _date_param(self, value: Any) -> Any:
        if self._dialect_name() == "sqlite" and value is not None:
            return str(value)
        return value

    # 단지 위치 조회: Complex entity 반환
    def find_location(
        self,
        criteria: SimpleLookupCriteria,
    ) -> Complex:
        complex_obj = self._resolve_complex(criteria.target_name)

        if (
            complex_obj.address is None
            and complex_obj.latitude is None
            and complex_obj.longitude is None
        ):
            raise SimpleLookupError(
                "no_result",
                "해당 단지의 위치 정보가 없습니다.",
            )

        return complex_obj

    # 단지 실거래 내역 조회: Complex entity + Trade entity 목록 반환
    def find_trade_history(
        self,
        criteria: SimpleLookupCriteria,
    ) -> tuple[Complex, list[Trade]]:
        complex_obj = self._resolve_complex(criteria.target_name)

        stmt = select(Trade).where(Trade.complex_id == complex_obj.id)
        stmt = self._apply_trade_filters(stmt, criteria)

        deal_date = self._deal_date_order_expression()

        if criteria.sort_order == SORT_OLDEST:
            stmt = stmt.order_by(deal_date.asc())
        else:
            stmt = stmt.order_by(deal_date.desc())

        stmt = stmt.limit(criteria.limit)
        trades = list(self.session.scalars(stmt).all())

        if not trades:
            raise SimpleLookupError(
                "no_result",
                "조건에 맞는 실거래 내역이 없습니다.",
            )

        return complex_obj, trades

    # 지역 최신 실거래 내역 조회: region에 속한 Complex + Trade 목록 반환
    def find_region_trade_history(
        self,
        criteria: SimpleLookupCriteria,
    ) -> list[dict[str, Any]]:
        region_obj = self._resolve_region(
            criteria.target_name,
            target_type=criteria.target_type,
        )

        stmt = (
            select(Trade, Complex)
            .join(Complex, Complex.id == Trade.complex_id)
        )
        if region_obj.type == "district":
            stmt = stmt.where(Complex.region_id == region_obj.id)
        elif region_obj.type == "neighborhood":
            pnu_prefix = f"{region_obj.code}%"
            stmt = stmt.where(
                (Complex.pnu.like(pnu_prefix))
                | (Complex.address.like(f"{region_obj.name}%"))
            )
        else:
            raise SimpleLookupError(
                "invalid_request",
                "동/구 단위 지역만 조회할 수 있습니다.",
            )

        stmt = self._apply_trade_filters(stmt, criteria)
        deal_date = self._deal_date_order_expression()
        if criteria.sort_order == SORT_OLDEST:
            stmt = stmt.order_by(deal_date.asc(), Trade.id.asc())
        else:
            stmt = stmt.order_by(deal_date.desc(), Trade.id.desc())

        rows = [
            {
                "trade": trade,
                "complex": complex_obj,
            }
            for trade, complex_obj in self.session.execute(
                stmt.limit(criteria.limit)
            ).all()
        ]

        if not rows:
            raise SimpleLookupError(
                "no_result",
                "조건에 맞는 지역 실거래 내역이 없습니다.",
            )

        return rows

    # 단지 최고가/최저가 조회: Complex entity + Trade entity 목록 반환
    def find_complex_price_record(
        self,
        criteria: SimpleLookupCriteria,
    ) -> tuple[Complex, list[Trade]]:
        complex_obj = self._resolve_complex(criteria.target_name)

        stmt = select(Trade).where(Trade.complex_id == complex_obj.id)
        stmt = self._apply_trade_filters(stmt, criteria)

        amount_order = (
            Trade.deal_amount.asc()
            if criteria.price_order == PRICE_LOWEST
            else Trade.deal_amount.desc()
        )

        deal_date = self._deal_date_order_expression()

        if criteria.sort_order == SORT_OLDEST:
            date_order = deal_date.asc()
        else:
            date_order = deal_date.desc()

        stmt = (
            stmt
            .order_by(amount_order, date_order)
            .limit(criteria.limit)
        )

        trades = list(self.session.scalars(stmt).all())

        if not trades:
            raise SimpleLookupError(
                "no_result",
                "조건에 맞는 단지 최고가/최저가 거래가 없습니다.",
            )

        return complex_obj, trades

    # 지역 최고가/최저가 랭킹 조회: raw SQL row 목록 반환
    def find_region_price_ranking(
        self,
        criteria: SimpleLookupCriteria,
    ) -> list[Mapping[str, Any]]:
        region_obj = self._resolve_region(criteria.target_name)

        amount_order = "ASC" if criteria.price_order == PRICE_LOWEST else "DESC"

        filters: list[str] = []
        params: dict[str, Any] = {
            "region_id": region_obj.id,
            "region_name": region_obj.name,
            "limit": criteria.limit,
        }

        if criteria.start_date is not None:
            filters.append(
                "AND t.deal_date >= :start_date"
                if self._dialect_name() == "sqlite"
                else "AND t.deal_date::date >= :start_date"
            )
            params["start_date"] = self._date_param(criteria.start_date)

        if criteria.end_date is not None:
            filters.append(
                "AND t.deal_date <= :end_date"
                if self._dialect_name() == "sqlite"
                else "AND t.deal_date::date <= :end_date"
            )
            params["end_date"] = self._date_param(criteria.end_date)

        if criteria.area_min is not None:
            filters.append("AND t.excl_area >= :area_min")
            params["area_min"] = criteria.area_min

        if criteria.area_max is not None:
            filters.append("AND t.excl_area <= :area_max")
            params["area_max"] = criteria.area_max

        filter_sql = "\n".join(filters)

        stmt = text(
            f"""
            SELECT
                ROW_NUMBER() OVER (
                    ORDER BY
                        t.deal_amount {amount_order}
                ) AS rank,
                :region_name AS region_name,
                c.id AS complex_id,
                c.name AS complex_name,
                c.trade_name AS trade_name,
                c.address AS address,
                t.id AS trade_id,
                t.deal_date AS deal_date,
                t.deal_amount AS deal_amount,
                t.excl_area AS excl_area,
                t.floor AS floor,
                t.apt_dong AS apt_dong
            FROM trades t
            JOIN complexes c
                ON c.id = t.complex_id
            WHERE c.region_id = :region_id
            {filter_sql}
            ORDER BY
                t.deal_amount {amount_order}
            LIMIT :limit
            """
        )

        rows = list(
            self.session.execute(stmt, params)
            .mappings()
            .all()
        )

        if not rows:
            raise SimpleLookupError(
                "no_result",
                "조건에 맞는 지역 최고가/최저가 거래가 없습니다.",
            )

        return rows

    # 단지명 확정: name 정확 → trade_name 정확 → name 부분 → trade_name 부분
    def _resolve_complex(self, target_name: str) -> Complex:
        search_steps = [
            (Complex.name, True),
            (Complex.trade_name, True),
            (Complex.name, False),
            (Complex.trade_name, False),
        ]

        for target in self._complex_name_variants(target_name):
            for column, exact in search_steps:
                # DB 단지명과 입력 단지명을 같은 검색용 형태로 맞춘다.
                compact_column = func.lower(func.replace(column, " ", ""))

                if exact:
                    stmt = select(Complex).where(
                        compact_column == target
                    )
                else:
                    stmt = select(Complex).where(
                        compact_column.like(f"%{target}%")
                    )

                stmt = (
                    stmt
                    .order_by(Complex.name.asc())
                    .limit(20)
                )

                rows = list(self.session.scalars(stmt).all())

                if len(rows) == 1:
                    return rows[0]

                if len(rows) > 1:
                    raise SimpleLookupError(
                        "ambiguous_target",
                        "여러 단지가 검색되었습니다. 더 구체적으로 입력해주세요.",
                        candidates=[
                            {
                                "complex_id": row.id,
                                "complex_name": row.name,
                                "trade_name": row.trade_name,
                                "address": row.address,
                            }
                            for row in rows
                        ],
                    )

        raise SimpleLookupError(
            "target_not_found",
            "조회 대상 단지를 찾을 수 없습니다.",
        )

    # 지역명 확정: 지역명 정확 일치, 기존 랭킹은 구 단위 부분 일치 호환 유지
    def _resolve_region(
        self,
        target_name: str,
        *,
        target_type: str | None = None,
    ) -> Region:
        target = normalize_region_search_text(target_name)
        candidates = [target]
        if target in {"강남", "서초", "송파"}:
            candidates.append(f"{target}구")
        candidates = list(dict.fromkeys(candidates))

        stmt = select(Region).where(Region.name.in_(candidates))
        if target_type in {"district", "neighborhood"}:
            stmt = stmt.where(Region.type == target_type)

        region = self.session.scalars(stmt.order_by(Region.id.asc()).limit(1)).first()

        if region is None and target_type is None:
            region = self.session.scalars(
                select(Region)
                .where(
                    Region.name.like(f"%{target}%"),
                    Region.type == "district",
                )
                .limit(1)
            ).first()

        if region is None:
            raise SimpleLookupError(
                "target_not_found",
                "조회 대상 지역을 찾을 수 없습니다.",
            )

        return region

    # 단지명 검색 후보 생성: 공백 제거 + 끝의 "아파트" 제거
    def _complex_name_variants(self, target_name: str) -> list[str]:
        target = normalize_complex_search_text(target_name)
        variants = [target]

        without_parentheses = re.sub(r"\([^)]*\)", "", target)
        if without_parentheses and without_parentheses != target:
            variants.append(without_parentheses)

        if target.endswith("아파트"):
            stripped = target.removesuffix("아파트")
            if stripped:
                variants.append(stripped)

        if without_parentheses.endswith("아파트"):
            stripped = without_parentheses.removesuffix("아파트")
            if stripped:
                variants.append(stripped)

        return list(dict.fromkeys(variants))

    # 기간/면적 필터를 Trade select statement에 적용
    def _apply_trade_filters(
        self,
        stmt: Any,
        criteria: SimpleLookupCriteria,
    ) -> Any:
        deal_date = self._deal_date_order_expression()

        if criteria.start_date is not None:
            stmt = stmt.where(deal_date >= self._date_param(criteria.start_date))

        if criteria.end_date is not None:
            stmt = stmt.where(deal_date <= self._date_param(criteria.end_date))

        if criteria.area_min is not None:
            stmt = stmt.where(Trade.excl_area >= criteria.area_min)

        if criteria.area_max is not None:
            stmt = stmt.where(Trade.excl_area <= criteria.area_max)

        return stmt


def normalize_complex_search_text(value: str) -> str:
    return "".join(str(value).split()).lower()


def normalize_region_search_text(value: str) -> str:
    return "".join(str(value).split())
