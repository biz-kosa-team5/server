"""시세추이와 가격 변화 조회에 필요한 DB 접근."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Integer, case, cast, func, literal, or_, select
from sqlalchemy.orm import Session

from app.chatbot.features.price_trend.dto import TrendCriteria, TrendError
from app.models import Complex, Region, Trade


class PriceTrendDao:
    """H4 조회에 필요한 SQL을 실행한다."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def find_complex_trend(
        self,
        criteria: TrendCriteria,
    ) -> list[dict[str, Any]]:
        """단지명으로 대상 단지를 확정하고 기간별 시세추이를 조회한다."""

        complex_id = self._resolve_complex_id(criteria.complex_name)
        statement = select(Trade).where(Trade.complex_id == complex_id)
        return self._find_trend(statement, criteria)

    def find_region_trend(
        self,
        criteria: TrendCriteria,
    ) -> list[dict[str, Any]]:
        """지역명으로 대상 지역을 확정하고 기간별 시세추이를 조회한다."""

        region_ids = self._resolve_region_ids(criteria.region_names)
        statement = (
            select(Trade)
            .join(Complex, Trade.complex_id == Complex.id)
            .where(Complex.region_id.in_(region_ids))
        )
        return self._find_trend(statement, criteria)

    def find_price_change_ranking(
        self,
        criteria: TrendCriteria,
    ) -> list[dict[str, Any]]:
        """지역 내 단지별 시작·종료 가격을 비교해 변화율 순위를 반환한다."""

        region_ids = self._resolve_region_ids(criteria.region_names)
        _validate_change_ranking_criteria(criteria)

        start_condition = Trade.deal_date.between(
            str(criteria.start_window_start),
            str(criteria.start_window_end),
        )
        end_condition = Trade.deal_date.between(
            str(criteria.end_window_start),
            str(criteria.end_window_end),
        )
        price_per_sqm = Trade.deal_amount / func.nullif(Trade.excl_area, 0)

        start_price = func.avg(case((start_condition, price_per_sqm), else_=None)).label("start_avg_price_per_sqm")
        end_price = func.avg(case((end_condition, price_per_sqm), else_=None)).label("end_avg_price_per_sqm")
        start_count = func.count(case((start_condition, Trade.id), else_=None)).label("start_trade_count")
        end_count = func.count(case((end_condition, Trade.id), else_=None)).label("end_trade_count")

        statement = (
            select(
                Complex.id.label("complex_id"),
                Complex.name.label("complex_name"),
                Complex.address.label("address"),
                start_price,
                end_price,
                start_count,
                end_count,
                func.avg(Trade.excl_area).label("avg_exclusive_area"),
            )
            .join(Trade, Trade.complex_id == Complex.id)
            .where(Complex.region_id.in_(region_ids))
            .where(or_(start_condition, end_condition))
        )
        statement = _apply_area_filters(statement, criteria)
        statement = (
            statement
            .group_by(Complex.id, Complex.name, Complex.address)
            .having(start_count >= int(criteria.min_trade_count))
            .having(end_count >= int(criteria.min_trade_count))
            .having(start_price > 0)
        )

        candidates: list[dict[str, Any]] = []
        for row in self.session.execute(statement).all():
            start_value = float(row.start_avg_price_per_sqm)
            end_value = float(row.end_avg_price_per_sqm)
            change_amount = end_value - start_value
            change_rate = change_amount / start_value * 100

            candidates.append(
                {
                    "complex_id": int(row.complex_id),
                    "complex_name": row.complex_name,
                    "address": row.address,
                    "start_avg_price_per_sqm": round(start_value, 2),
                    "end_avg_price_per_sqm": round(end_value, 2),
                    "change_amount": round(change_amount, 2),
                    "_raw_change_rate": change_rate,
                    "start_trade_count": int(row.start_trade_count),
                    "end_trade_count": int(row.end_trade_count),
                    "avg_exclusive_area": round(float(row.avg_exclusive_area), 2),
                }
            )

        ranked_candidates = _sort_change_candidates(
            candidates,
            direction=str(criteria.change_direction),
        )

        items: list[dict[str, Any]] = []
        for rank, row in enumerate(ranked_candidates[: int(criteria.limit)], start=1):
            raw_change_rate = row.pop("_raw_change_rate")
            items.append(
                {
                    "rank": rank,
                    **row,
                    "change_rate": round(raw_change_rate, 2),
                }
            )

        return items

    def _resolve_complex_id(self, complex_name: str | None) -> int:
        """단지명을 정확 일치, 부분 일치 순서로 검색해 단지 ID를 확정한다."""

        if complex_name is None:
            raise ValueError("단지명이 없는 단지 시세추이 조건입니다.")

        exact = self._find_complexes(complex_name, partial=False)
        if len(exact) == 1:
            return exact[0].id
        if len(exact) > 1:
            raise _ambiguous_complex(exact)

        partial = self._find_complexes(complex_name, partial=True)
        if len(partial) == 1:
            return partial[0].id
        if len(partial) > 1:
            raise _ambiguous_complex(partial)

        raise TrendError(
            "target_not_found",
            "입력한 이름과 일치하는 아파트 단지를 찾지 못했습니다.",
        )

    def _resolve_region_ids(self, region_names: tuple[str, ...]) -> list[int]:
        """지역명을 정확 일치, 부분 일치 순서로 검색해 지역 ID 목록을 확정한다."""

        region_ids: list[int] = []

        for name in region_names:
            exact = self._find_regions(name, partial=False)
            candidates = exact or self._find_regions(name, partial=True)

            if not candidates:
                raise TrendError(
                    "target_not_found",
                    f"입력한 이름과 일치하는 지역을 찾지 못했습니다: {name}",
                )
            if len(candidates) > 1:
                raise _ambiguous_region(candidates)

            region_id = candidates[0].id
            if region_id not in region_ids:
                region_ids.append(region_id)

        return region_ids

    def _find_complexes(
        self,
        name: str,
        *,
        partial: bool,
    ) -> list[Complex]:
        """이름으로 단지 후보를 조회한다."""

        normalized = _normalize_search_name(name)
        name_expression = _normalized_name_expression(Complex.name)
        trade_name_expression = _normalized_name_expression(Complex.trade_name)

        if partial:
            pattern = f"%{_escape_like_pattern(normalized)}%"
            condition = or_(
                name_expression.like(pattern, escape="\\"),
                trade_name_expression.like(pattern, escape="\\"),
            )
        else:
            condition = or_(
                name_expression == normalized,
                trade_name_expression == normalized,
            )

        statement = (
            select(Complex)
            .where(condition)
            .order_by(Complex.name, Complex.id)
            .limit(20)
        )

        return list(self.session.scalars(statement).all())

    def _find_regions(
        self,
        name: str,
        *,
        partial: bool,
    ) -> list[Region]:
        """이름으로 지역 후보를 조회한다."""

        normalized = _normalize_search_name(name)
        expression = _normalized_name_expression(Region.name)

        if partial:
            pattern = f"%{_escape_like_pattern(normalized)}%"
            condition = expression.like(pattern, escape="\\")
        else:
            condition = expression == normalized

        statement = (
            select(Region)
            .where(condition)
            .order_by(Region.name, Region.id)
            .limit(20)
        )

        return list(self.session.scalars(statement).all())

    def _find_trend(
        self,
        trade_statement,
        criteria: TrendCriteria,
    ) -> list[dict[str, Any]]:
        """단지·지역 시세추이 집계 SQL을 실행한다."""

        if criteria.interval is None:
            raise ValueError("시계열 조회에는 interval이 필요합니다.")

        period_expression = _period_start_expression(criteria.interval)
        price_per_sqm = Trade.deal_amount / func.nullif(Trade.excl_area, 0)

        statement = trade_statement.with_only_columns(
            period_expression.label("period_start"),
            func.avg(Trade.deal_amount).label("avg_deal_amount"),
            func.avg(price_per_sqm).label("avg_price_per_sqm"),
            func.min(Trade.deal_amount).label("min_deal_amount"),
            func.max(Trade.deal_amount).label("max_deal_amount"),
            func.count(Trade.id).label("trade_count"),
            func.avg(Trade.excl_area).label("avg_exclusive_area"),
            maintain_column_froms=True,
        )
        statement = _apply_trade_filters(statement, criteria)
        statement = statement.group_by(period_expression).order_by(period_expression)

        return [
            {
                "period_start": str(row.period_start),
                "avg_deal_amount": round(float(row.avg_deal_amount), 2),
                "avg_price_per_sqm": round(float(row.avg_price_per_sqm), 2),
                "min_deal_amount": int(row.min_deal_amount),
                "max_deal_amount": int(row.max_deal_amount),
                "trade_count": int(row.trade_count),
                "avg_exclusive_area": round(float(row.avg_exclusive_area), 2),
            }
            for row in self.session.execute(statement).all()
        ]


def _validate_change_ranking_criteria(criteria: TrendCriteria) -> None:
    """가격 변화율 조회에 필요한 Criteria 필드를 확인한다."""

    required = (
        criteria.start_window_start,
        criteria.start_window_end,
        criteria.end_window_start,
        criteria.end_window_end,
        criteria.change_direction,
        criteria.limit,
        criteria.min_trade_count,
    )

    if any(value is None for value in required):
        raise ValueError("가격 변화율 조회 조건이 완성되지 않았습니다.")


def _sort_change_candidates(
    candidates: list[dict[str, Any]],
    *,
    direction: str,
) -> list[dict[str, Any]]:
    """가격 변화 방향에 맞게 후보를 필터링하고 정렬한다."""

    if direction == "up":
        filtered = [
            row for row in candidates
            if row["_raw_change_rate"] > 0
        ]
        filtered.sort(key=lambda row: (-row["_raw_change_rate"], row["complex_id"]))
        return filtered

    if direction == "down":
        filtered = [
            row for row in candidates
            if row["_raw_change_rate"] < 0
        ]
        filtered.sort(key=lambda row: (row["_raw_change_rate"], row["complex_id"]))
        return filtered

    filtered = [
        row for row in candidates
        if row["_raw_change_rate"] != 0
    ]
    filtered.sort(key=lambda row: (-abs(row["_raw_change_rate"]), row["complex_id"]))
    return filtered


def _apply_trade_filters(statement, criteria: TrendCriteria):
    """기간 조건과 면적 조건을 거래 조회에 적용한다."""

    statement = statement.where(Trade.deal_date >= criteria.start_date)
    statement = statement.where(Trade.deal_date <= criteria.end_date)
    return _apply_area_filters(statement, criteria)


def _apply_area_filters(statement, criteria: TrendCriteria):
    """면적 범위 조건을 거래 조회에 적용한다."""

    if criteria.area_min is not None:
        statement = statement.where(Trade.excl_area >= criteria.area_min)
    if criteria.area_max is not None:
        statement = statement.where(Trade.excl_area <= criteria.area_max)
    return statement


def _period_start_expression(interval: str):
    """거래일 문자열을 집계 구간 시작일 문자열로 변환한다."""

    year = func.substr(Trade.deal_date, 1, 4)

    if interval == "month":
        return func.substr(Trade.deal_date, 1, 7) + literal("-01")

    if interval == "quarter":
        month = cast(func.substr(Trade.deal_date, 6, 2), Integer)
        quarter_month = case(
            (month <= 3, literal("01")),
            (month <= 6, literal("04")),
            (month <= 9, literal("07")),
            else_=literal("10"),
        )
        return year + literal("-") + quarter_month + literal("-01")

    if interval == "year":
        return year + literal("-01-01")

    raise ValueError(f"지원하지 않는 interval입니다: {interval}")


def _normalize_search_name(value: str) -> str:
    """검색용 이름에서 공백을 제거하고 소문자로 변환한다."""

    return "".join(value.lower().split())


def _normalized_name_expression(column):
    """DB 컬럼을 검색용 이름과 같은 방식으로 정규화한다."""

    return func.lower(func.replace(func.coalesce(column, ""), " ", ""))


def _escape_like_pattern(value: str) -> str:
    """LIKE 검색 특수문자를 이스케이프한다."""

    return (
        value
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _ambiguous_complex(candidates: list[Complex]) -> TrendError:
    """중복 단지 후보를 ambiguous_target 에러로 변환한다."""

    return TrendError(
        "ambiguous_target",
        "같은 이름 또는 유사한 이름의 아파트 단지가 여러 개 있습니다.",
        candidates=[
            {
                "target_type": "complex",
                "complex_id": row.id,
                "complex_name": row.name,
                "address": row.address,
            }
            for row in candidates
        ],
    )


def _ambiguous_region(candidates: list[Region]) -> TrendError:
    """중복 지역 후보를 ambiguous_target 에러로 변환한다."""

    return TrendError(
        "ambiguous_target",
        "같은 이름 또는 유사한 이름의 지역이 여러 개 있습니다.",
        candidates=[
            {
                "target_type": "region",
                "region_id": row.id,
                "region_name": row.name,
            }
            for row in candidates
        ],
    )
