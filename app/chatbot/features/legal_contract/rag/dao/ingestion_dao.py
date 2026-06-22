from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..model import DailyLegalTermMapping, LawDocument, RawApiResponse
from ..parser import ParsedDocument


class LegalDataDao:
  def __init__(self, session: Session): self.session = session

  def add_raw(self, **values: Any) -> RawApiResponse:
    row = RawApiResponse(**values); self.session.add(row); return row

  def pending_raw(self, raw_ids: list[int] | None) -> list[RawApiResponse]:
    statuses = ("SUCCESS", "PARSE_FAILED", "PARSED", "SKIPPED") if raw_ids else ("SUCCESS", "PARSE_FAILED")
    query = select(RawApiResponse).where(RawApiResponse.source_type == "law_api", RawApiResponse.target == "eflaw", RawApiResponse.status.in_(statuses))
    if raw_ids: query = query.where(RawApiResponse.id.in_(raw_ids))
    return list(self.session.scalars(query.order_by(RawApiResponse.id)).all())

  def upsert_document(self, value: ParsedDocument) -> None:
    row = self.session.scalar(select(LawDocument).where(LawDocument.law_id == value.law_id,
      LawDocument.effective_date == value.effective_date, LawDocument.article_no == value.article_no,
      LawDocument.paragraph_no == value.paragraph_no))
    data = vars(value).copy(); data["document_metadata"] = data.pop("metadata")
    parent_document_id = None
    if value.doc_type == "paragraph":
      parent_document_id = self.session.scalar(select(LawDocument.id).where(
        LawDocument.law_id == value.law_id,
        LawDocument.effective_date == value.effective_date,
        LawDocument.article_no == value.article_no,
        LawDocument.paragraph_no == "",
      ))
      if parent_document_id is None:
        raise ValueError(f"Parent article not found for {value.law_name} {value.article_no}")
    data["parent_document_id"] = parent_document_id
    if row is None:
      self.session.add(LawDocument(**data))
      if value.doc_type == "article":
        self.session.flush()
      return
    for key, item in data.items(): setattr(row, key, item)
    row.parse_status = "PARSED"; row.parse_error = None

  def pending_term_raw(self, raw_ids: list[int] | None) -> list[RawApiResponse]:
    statuses = ("SUCCESS", "PARSE_FAILED", "PARSED") if raw_ids else ("SUCCESS", "PARSE_FAILED")
    query = select(RawApiResponse).where(
      RawApiResponse.source_type == "term_mapping_api",
      RawApiResponse.target == "dlytrmRlt",
      RawApiResponse.status.in_(statuses),
    )
    if raw_ids:
      query = query.where(RawApiResponse.id.in_(raw_ids))
    return list(self.session.scalars(query.order_by(RawApiResponse.id)).all())

  def upsert_mapping(self, daily: str, legal: str, relation: str, priority: int,
    raw_data: dict[str, Any] | None = None) -> bool:
    row = self.session.scalar(select(DailyLegalTermMapping).where(DailyLegalTermMapping.daily_term == daily,
      DailyLegalTermMapping.legal_term == legal, DailyLegalTermMapping.relation_type == relation))
    if row is None:
      self.session.add(DailyLegalTermMapping(daily_term=daily, legal_term=legal, relation_type=relation,
        domain="apartment_sale", priority=priority, raw_data=raw_data or {"source": "curated_mvp"})); return True
    row.priority = priority; row.domain = "apartment_sale"
    if raw_data is not None: row.raw_data = raw_data
    return False

  def list_raw(self, query: str | None, target: str | None, limit: int, offset: int):
    stmt = select(RawApiResponse).order_by(RawApiResponse.id.desc())
    if query: stmt = stmt.where(RawApiResponse.query == query)
    if target: stmt = stmt.where(RawApiResponse.target == target)
    return list(self.session.scalars(stmt.limit(limit).offset(offset)).all())

  def list_documents(self, law_name: str | None, effective: date | None, status: str | None, limit: int, offset: int):
    stmt = select(LawDocument).order_by(LawDocument.id)
    if law_name: stmt = stmt.where(LawDocument.law_name == law_name)
    if effective: stmt = stmt.where(LawDocument.effective_date == effective)
    if status: stmt = stmt.where(LawDocument.parse_status == status)
    return list(self.session.scalars(stmt.limit(limit).offset(offset)).all())

  def list_mappings(self, daily: str | None, limit: int, offset: int):
    stmt = select(DailyLegalTermMapping).order_by(DailyLegalTermMapping.priority.desc(), DailyLegalTermMapping.id)
    if daily: stmt = stmt.where(DailyLegalTermMapping.daily_term == daily)
    return list(self.session.scalars(stmt.limit(limit).offset(offset)).all())

  def commit(self): self.session.commit()
  def rollback(self): self.session.rollback()
