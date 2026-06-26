from __future__ import annotations

from typing import Any

from sqlalchemy import Integer, case, cast, func, literal, or_, select
from sqlalchemy.orm import Session

from app.chatbot.features.price_trend.dto import (
    RANK_BY_CHANGE_RATE,
    RANK_BY_MIN_DEAL_AMOUNT,
    TARGET_COMPLEX,
    TARGET_REGION,
    TrendAnalysisSpec,
    TrendError,
)
from app.models import Complex, Region, Trade


GANGNAM_3 = ("강남구", "서초구", "송파구")


class PriceTrendDao:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_timeseries(self, spec: TrendAnalysisSpec) -> list[dict[str, Any]]:
        statement = self._timeseries_statement(spec)
        return [_trend_row(row) for row in self.session.execute(statement).all()]

    def find_ranking(self, spec: TrendAnalysisSpec) -> list[dict[str, Any]]:
        if spec.rank_by == RANK_BY_CHANGE_RATE:
            rows = self.session.execute(self._change_rate_statement(spec)).all()
            return _change_rate_rows(rows, direction=str(spec.direction), limit=int(spec.limit or 5))

        rows = self.session.execute(self._price_ranking_statement(spec)).all()
        return [_price_rank_row(rank, row, str(spec.rank_by)) for rank, row in enumerate(rows, start=1)]

    def _timeseries_statement(self, spec: TrendAnalysisSpec):
        period = _period_expr(str(spec.interval))
        price_per_sqm = _price_per_sqm_expr()

        statement = (
            select(
                period.label("period_start"),
                func.avg(Trade.deal_amount).label("avg_deal_amount"),
                func.avg(price_per_sqm).label("avg_price_per_sqm"),
                func.count(Trade.id).label("trade_count"),
            )
            .select_from(Trade)
            .join(Complex, Trade.complex_id == Complex.id)
        )

        if spec.target_type == TARGET_COMPLEX:
            complex_row = self._resolve_complex(spec.target_name)
            statement = statement.where(Complex.id == complex_row.id)
        else:
            region_ids = self._resolve_region_ids(spec.target_name)
            statement = statement.where(Complex.region_id.in_(region_ids))

        return _apply_filters(statement, spec).group_by(period).order_by(period)

    def _change_rate_statement(self, spec: TrendAnalysisSpec):
        region_ids = self._resolve_region_ids(spec.target_name)
        start_cond = Trade.deal_date.between(str(spec.start_window_start), str(spec.start_window_end))
        end_cond = Trade.deal_date.between(str(spec.end_window_start), str(spec.end_window_end))
        price_per_sqm = _price_per_sqm_expr()

        start_price = func.avg(case((start_cond, price_per_sqm), else_=None)).label("start_price")
        end_price = func.avg(case((end_cond, price_per_sqm), else_=None)).label("end_price")
        start_count = func.count(case((start_cond, Trade.id), else_=None)).label("start_count")
        end_count = func.count(case((end_cond, Trade.id), else_=None)).label("end_count")

        statement = (
            select(
                Complex.id.label("complex_id"),
                Complex.name.label("complex_name"),
                Complex.address.label("address"),
                start_price,
                end_price,
                start_count,
                end_count,
            )
            .join(Trade, Trade.complex_id == Complex.id)
            .where(Complex.region_id.in_(region_ids))
            .where(or_(start_cond, end_cond))
        )

        return (
            _apply_area_filters(statement, spec)
            .group_by(Complex.id, Complex.name, Complex.address)
            .having(start_count >= int(spec.min_trade_count or 1))
            .having(end_count >= int(spec.min_trade_count or 1))
            .having(start_price > 0)
        )

    def _price_ranking_statement(self, spec: TrendAnalysisSpec):
        region_ids = self._resolve_region_ids(spec.target_name)
        metric = func.min(Trade.deal_amount) if spec.rank_by == RANK_BY_MIN_DEAL_AMOUNT else func.max(Trade.deal_amount)
        label = "min_deal_amount" if spec.rank_by == RANK_BY_MIN_DEAL_AMOUNT else "max_deal_amount"
        order_metric = metric.asc() if spec.direction == "asc" else metric.desc()

        statement = (
            select(
                Complex.id.label("complex_id"),
                Complex.name.label("complex_name"),
                Complex.address.label("address"),
                metric.label(label),
                func.count(Trade.id).label("trade_count"),
            )
            .join(Trade, Trade.complex_id == Complex.id)
            .where(Complex.region_id.in_(region_ids))
        )

        return (
            _apply_filters(statement, spec)
            .group_by(Complex.id, Complex.name, Complex.address)
            .order_by(order_metric, Complex.id)
            .limit(int(spec.limit or 5))
        )

    def _resolve_complex(self, name: str) -> Complex:
        row = self._find_complex(name)
        if row is None:
            raise TrendError("target_not_found", "입력한 이름과 일치하는 아파트 단지를 찾지 못했습니다.")
        return row

    def _resolve_region_ids(self, name: str) -> list[int]:
        names = GANGNAM_3 if _normalize_name(name) in {"강남3구", "강남삼구"} else (name,)
        return [self._resolve_region(region_name).id for region_name in names]

    def _resolve_region(self, name: str) -> Region:
        row = self._find_region(name)
        if row is None:
            raise TrendError("target_not_found", f"입력한 이름과 일치하는 지역을 찾지 못했습니다: {name}")
        return row

    def _find_complex(self, name: str) -> Complex | None:
        statement = (
            select(Complex)
            .where(or_(Complex.name == name, Complex.trade_name == name))
            .order_by(Complex.id)
            .limit(1)
        )
        return self.session.scalars(statement).first()

    def _find_region(self, name: str) -> Region | None:
        statement = select(Region).where(Region.name == name).order_by(Region.id).limit(1)
        return self.session.scalars(statement).first()


def _trend_row(row: Any) -> dict[str, Any]:
    return {
        "period_start": str(row.period_start),
        "avg_deal_amount": round(float(row.avg_deal_amount), 2),
        "avg_price_per_sqm": round(float(row.avg_price_per_sqm), 2),
        "trade_count": int(row.trade_count),
    }


def _change_rate_rows(rows: list[Any], *, direction: str, limit: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        start = float(row.start_price)
        end = float(row.end_price)
        rate = (end - start) / start * 100
        if (direction == "desc" and rate <= 0) or (direction == "asc" and rate >= 0):
            continue
        items.append({
            "complex_id": int(row.complex_id),
            "complex_name": row.complex_name,
            "address": row.address,
            "start_price_per_sqm": round(start, 2),
            "end_price_per_sqm": round(end, 2),
            "change_amount": round(end - start, 2),
            "change_rate": round(rate, 2),
            "trade_counts": {"start": int(row.start_count), "end": int(row.end_count)},
        })

    if direction == "desc":
        items.sort(key=lambda item: (-item["change_rate"], item["complex_id"]))
    else:
        items.sort(key=lambda item: (item["change_rate"], item["complex_id"]))
    return [{"rank": rank, **item} for rank, item in enumerate(items[:limit], start=1)]


def _price_rank_row(rank: int, row: Any, rank_by: str) -> dict[str, Any]:
    amount_key = "min_deal_amount" if rank_by == RANK_BY_MIN_DEAL_AMOUNT else "max_deal_amount"
    return {
        "rank": rank,
        "complex_id": int(row.complex_id),
        "complex_name": row.complex_name,
        "address": row.address,
        amount_key: int(getattr(row, amount_key)),
        "trade_counts": {"total": int(row.trade_count)},
    }


def _apply_filters(statement, spec: TrendAnalysisSpec):
    return _apply_area_filters(
        statement.where(Trade.deal_date >= spec.start_date).where(Trade.deal_date <= spec.end_date),
        spec,
    )


def _apply_area_filters(statement, spec: TrendAnalysisSpec):
    if spec.area_min is not None:
        statement = statement.where(Trade.excl_area >= spec.area_min)
    if spec.area_max is not None:
        statement = statement.where(Trade.excl_area <= spec.area_max)
    return statement


def _period_expr(interval: str):
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


def _price_per_sqm_expr():
    return Trade.deal_amount / func.nullif(Trade.excl_area, 0)


def _normalize_name(value: str) -> str:
    return "".join(value.lower().split())
