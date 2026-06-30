"""price_trend DAO 모듈.

policy가 확정한 criteria를 바탕으로 고정 SQL을 실행한다.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.chatbot.features.complex_resolver import (
    AMBIGUOUS,
    INSUFFICIENT_QUERY,
    NOT_FOUND,
    ComplexResolver,
)

from .dto import (
    RANK_BY_CHANGE_RATE,
    TARGET_COMPLEX,
    TARGET_REGION,
    TrendCriteria,
    TrendError,
)


class PriceTrendDao:
    """price_trend 조회용 DAO."""

    def _dialect_name(self, session: Session) -> str:
        bind = session.get_bind()
        return bind.dialect.name if bind is not None else ""

    def _period_expression(self, interval: str, dialect_name: str) -> str:
        if dialect_name == "sqlite":
            if interval == "month":
                return "substr(t.deal_date, 1, 7) || '-01'"
            if interval == "quarter":
                return (
                    "strftime('%Y', t.deal_date) || '-' || "
                    "printf('%02d', (CAST(((CAST(strftime('%m', t.deal_date) AS INTEGER) - 1) / 3) AS INTEGER) * 3 + 1)) "
                    "|| '-01'"
                )
            if interval == "year":
                return "strftime('%Y', t.deal_date) || '-01-01'"

        if interval == "month":
            return "date_trunc('month', CAST(t.deal_date AS timestamp))::date"
        if interval == "quarter":
            return "date_trunc('quarter', CAST(t.deal_date AS timestamp))::date"
        if interval == "year":
            return "date_trunc('year', CAST(t.deal_date AS timestamp))::date"

        raise TrendError(
            "invalid_condition",
            "지원하지 않는 시계열 구간입니다.",
        )

    def _monthly_expression(self, dialect_name: str) -> str:
        if dialect_name == "sqlite":
            return "substr(t.deal_date, 1, 7) || '-01'"
        return "date_trunc('month', CAST(t.deal_date AS timestamp))::date"

    def _date_area_filter(self, dialect_name: str) -> str:
        if dialect_name == "sqlite":
            return """
                  AND t.deal_date >= :start_date
                  AND t.deal_date <= :end_date
                  AND (:area_min IS NULL OR t.excl_area >= :area_min)
                  AND (:area_max IS NULL OR t.excl_area <= :area_max)
            """

        return """
                  AND CAST(t.deal_date AS date) >= :start_date
                  AND CAST(t.deal_date AS date) <= :end_date
                  AND (CAST(:area_min AS numeric) IS NULL OR t.excl_area >= CAST(:area_min AS numeric))
                  AND (CAST(:area_max AS numeric) IS NULL OR t.excl_area <= CAST(:area_max AS numeric))
        """

    def _criteria_params(
        self,
        criteria: TrendCriteria,
        dialect_name: str,
    ) -> dict[str, Any]:
        start_date: Any = criteria["start_date"]
        end_date: Any = criteria["end_date"]
        if dialect_name == "sqlite":
            start_date = str(start_date)
            end_date = str(end_date)

        return {
            "start_date": start_date,
            "end_date": end_date,
            "area_min": criteria.get("area_min"),
            "area_max": criteria.get("area_max"),
        }

    def _partial_complex_statement(self, dialect_name: str):
        if dialect_name == "sqlite":
            return text(
                """
                SELECT id, name, trade_name, address
                FROM complexes
                WHERE lower(name) LIKE '%' || lower(:target_name) || '%'
                OR lower(coalesce(trade_name, '')) LIKE '%' || lower(:target_name) || '%'
                ORDER BY
                    CASE
                        WHEN lower(name) LIKE lower(:target_name) || '%' THEN 0
                        WHEN lower(coalesce(trade_name, '')) LIKE lower(:target_name) || '%' THEN 1
                        WHEN lower(name) LIKE '%' || lower(:target_name) || '%' THEN 2
                        WHEN lower(coalesce(trade_name, '')) LIKE '%' || lower(:target_name) || '%' THEN 3
                        ELSE 4
                    END,
                    id
                LIMIT 10
                """
            )

        return text(
            """
            SELECT id, name, trade_name, address
            FROM complexes
            WHERE name ILIKE '%' || :target_name || '%'
            OR trade_name ILIKE '%' || :target_name || '%'
            ORDER BY
                CASE
                    WHEN name ILIKE :target_name || '%' THEN 0
                    WHEN trade_name ILIKE :target_name || '%' THEN 1
                    WHEN name ILIKE '%' || :target_name || '%' THEN 2
                    WHEN trade_name ILIKE '%' || :target_name || '%' THEN 3
                    ELSE 4
                END,
                id
            LIMIT 10
            """
        )

    def find_timeseries(
        self,
        session: Session,
        criteria: TrendCriteria,
    ) -> list[dict[str, Any]]:
        """시계열 데이터를 조회한다."""

        target = self._resolve_target(session, criteria)

        dialect_name = self._dialect_name(session)
        period_expr = self._period_expression(criteria["interval"], dialect_name)
        date_area_filter = self._date_area_filter(dialect_name)
        params: dict[str, Any] = self._criteria_params(criteria, dialect_name)

        if target["target_type"] == TARGET_COMPLEX:
            target_filter = "c.id = :complex_id"
            params["complex_id"] = target["complex_id"]
            statement = text(
                f"""
                SELECT
                    {period_expr} AS period_start,
                    AVG(t.deal_amount) AS avg_deal_amount,
                    AVG(t.deal_amount / NULLIF(t.excl_area, 0)) AS avg_price_per_sqm,
                    COUNT(t.id) AS trade_count
                FROM trades t
                JOIN complexes c ON c.id = t.complex_id
                WHERE {target_filter}
                {date_area_filter}
                GROUP BY period_start
                ORDER BY period_start
                """
            )
        else:
            target_filter = "c.region_id IN :region_ids"
            params["region_ids"] = target["region_ids"]
            statement = text(
                f"""
                SELECT
                    {period_expr} AS period_start,
                    AVG(t.deal_amount) AS avg_deal_amount,
                    AVG(t.deal_amount / NULLIF(t.excl_area, 0)) AS avg_price_per_sqm,
                    COUNT(t.id) AS trade_count
                FROM trades t
                JOIN complexes c ON c.id = t.complex_id
                WHERE {target_filter}
                {date_area_filter}
                GROUP BY period_start
                ORDER BY period_start
                """
            ).bindparams(bindparam("region_ids", expanding=True))

        rows = session.execute(statement, params).mappings().all()

        return [
            {
                "period_start": str(row["period_start"]),
                "avg_deal_amount": round(float(row["avg_deal_amount"]), 2),
                "avg_price_per_sqm": round(float(row["avg_price_per_sqm"]), 2),
                "trade_count": int(row["trade_count"]),
            }
            for row in rows
        ]

    def find_ranking(
        self,
        session: Session,
        criteria: TrendCriteria,
    ) -> list[dict[str, Any]]:
        """랭킹 데이터를 조회한다."""

        target = self._resolve_target(session, criteria)

        if target["target_type"] != TARGET_REGION:
            raise TrendError(
                "invalid_condition",
                "랭킹 조회는 지역 기준만 지원합니다.",
            )

        rank_by = criteria["rank_by"]
        direction = criteria["direction"]
        limit = criteria["limit"]
        dialect_name = self._dialect_name(session)
        month_expr = self._monthly_expression(dialect_name)
        date_area_filter = self._date_area_filter(dialect_name)

        params: dict[str, Any] = {
            "region_ids": target["region_ids"],
            "limit": limit,
        }
        params.update(self._criteria_params(criteria, dialect_name))

        if rank_by == RANK_BY_CHANGE_RATE:
            if direction == "asc":
                change_filter = "change_rate < 0"
                order_clause = "change_rate ASC, complex_id"
            else:
                change_filter = "change_rate > 0"
                order_clause = "change_rate DESC, complex_id"

            statement = text(
                f"""
                WITH monthly AS (
                    SELECT
                        c.id AS complex_id,
                        c.name AS complex_name,
                        c.address AS address,
                        {month_expr} AS period_start,
                        AVG(t.deal_amount / NULLIF(t.excl_area, 0)) AS avg_price_per_sqm,
                        COUNT(t.id) AS trade_count
                    FROM trades t
                    JOIN complexes c ON c.id = t.complex_id
                    WHERE c.region_id IN :region_ids
                    {date_area_filter}
                    GROUP BY
                        c.id,
                        c.name,
                        c.address,
                        period_start
                ),
                ranked_monthly AS (
                    SELECT
                        *,
                        ROW_NUMBER() OVER (
                            PARTITION BY complex_id
                            ORDER BY period_start ASC
                        ) AS start_rank,
                        ROW_NUMBER() OVER (
                            PARTITION BY complex_id
                            ORDER BY period_start DESC
                        ) AS end_rank
                    FROM monthly
                ),
                paired AS (
                    SELECT
                        start_row.complex_id,
                        start_row.complex_name,
                        start_row.address,
                        start_row.period_start AS start_period,
                        end_row.period_start AS end_period,
                        start_row.avg_price_per_sqm AS start_price_per_sqm,
                        end_row.avg_price_per_sqm AS end_price_per_sqm,
                        start_row.trade_count AS start_trade_count,
                        end_row.trade_count AS end_trade_count
                    FROM ranked_monthly start_row
                    JOIN ranked_monthly end_row
                      ON end_row.complex_id = start_row.complex_id
                    WHERE start_row.start_rank = 1
                      AND end_row.end_rank = 1
                      AND start_row.period_start < end_row.period_start
                      AND start_row.avg_price_per_sqm > 0
                      AND end_row.avg_price_per_sqm IS NOT NULL
                ),
                scored AS (
                    SELECT
                        complex_id,
                        complex_name,
                        address,
                        start_period,
                        end_period,
                        start_price_per_sqm,
                        end_price_per_sqm,
                        end_price_per_sqm - start_price_per_sqm AS change_amount,
                        (
                            (end_price_per_sqm - start_price_per_sqm)
                            / NULLIF(start_price_per_sqm, 0)
                            * 100
                        ) AS change_rate,
                        start_trade_count,
                        end_trade_count
                    FROM paired
                ),
                ordered AS (
                    SELECT
                        ROW_NUMBER() OVER (ORDER BY {order_clause}) AS rank,
                        *
                    FROM scored
                    WHERE {change_filter}
                )
                SELECT
                    rank,
                    complex_id,
                    complex_name,
                    address,
                    start_period,
                    end_period,
                    start_price_per_sqm,
                    end_price_per_sqm,
                    change_amount,
                    change_rate,
                    start_trade_count,
                    end_trade_count
                FROM ordered
                ORDER BY rank
                LIMIT :limit
                """
            ).bindparams(bindparam("region_ids", expanding=True))

            rows = session.execute(statement, params).mappings().all()

            return [
                {
                    "rank": int(row["rank"]),
                    "complex_id": int(row["complex_id"]),
                    "complex_name": row["complex_name"],
                    "address": row["address"],
                    "start_period": str(row["start_period"]),
                    "end_period": str(row["end_period"]),
                    "start_price_per_sqm": round(float(row["start_price_per_sqm"]), 2),
                    "end_price_per_sqm": round(float(row["end_price_per_sqm"]), 2),
                    "change_amount": round(float(row["change_amount"]), 2),
                    "change_rate": round(float(row["change_rate"]), 2),
                    "trade_counts": {
                        "start": int(row["start_trade_count"]),
                        "end": int(row["end_trade_count"]),
                    },
                }
                for row in rows
            ]

    def _resolve_target(
        self,
        session: Session,
        criteria: TrendCriteria,
    ) -> dict[str, Any]:
        """criteria의 target 조건을 DB id 조건으로 변환한다."""

        target_type = criteria["target_type"]
        target_name = criteria["target_name"]

        if target_type == TARGET_COMPLEX:
            resolution = ComplexResolver(session).resolve(target_name)
            if resolution.resolved and resolution.complex is not None:
                criteria["complex_id"] = resolution.complex.id
                criteria["resolved_complex_name"] = resolution.complex.name
                return {
                    "target_type": TARGET_COMPLEX,
                    "complex_id": resolution.complex.id,
                    "region_ids": None,
                }

            if resolution.status == AMBIGUOUS:
                raise TrendError(
                    "ambiguous_target",
                    resolution.message or "입력한 이름과 비슷한 아파트 단지가 여러 개 있습니다.",
                    candidates=resolution.candidates,
                )

            if resolution.status == INSUFFICIENT_QUERY:
                raise TrendError(
                    "insufficient_query",
                    resolution.message or "조회할 단지명이 부족합니다.",
                )

            if resolution.status == NOT_FOUND:
                raise TrendError(
                    "target_not_found",
                    resolution.message or "입력한 이름과 일치하는 아파트 단지를 찾지 못했습니다.",
                    candidates=resolution.candidates,
                )
            raise TrendError(
                "target_not_found",
                "입력한 이름과 일치하는 아파트 단지를 찾지 못했습니다.",
            )

        if target_type == TARGET_REGION:
            region_names = criteria.get("region_names") or [target_name]

            statement = text(
                """
                SELECT id, name
                FROM regions
                WHERE name IN :region_names
                ORDER BY id
                """
            ).bindparams(bindparam("region_names", expanding=True))

            rows = session.execute(
                statement,
                {"region_names": region_names},
            ).mappings().all()

            found_names = {row["name"] for row in rows}
            missing_names = [name for name in region_names if name not in found_names]

            if missing_names:
                raise TrendError(
                    "target_not_found",
                    f"입력한 이름과 일치하는 지역을 찾지 못했습니다: {missing_names[0]}",
                )

            return {
                "target_type": TARGET_REGION,
                "complex_id": None,
                "region_ids": [row["id"] for row in rows],
            }

        raise TrendError(
            "invalid_condition",
            "지원하지 않는 조회 대상 유형입니다.",
        )
