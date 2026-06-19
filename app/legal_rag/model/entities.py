from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ...models import Base


ID_TYPE = BigInteger().with_variant(Integer, "sqlite")


class RawApiResponse(Base):
  __tablename__ = "raw_api_responses"
  __table_args__ = (Index("idx_raw_api_responses_target", "target"), Index("idx_raw_api_responses_query", "query"))

  id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
  source_type: Mapped[str] = mapped_column(String(50), nullable=False)
  target: Mapped[str | None] = mapped_column(String(50))
  query: Mapped[str | None] = mapped_column(String(255))
  request_url: Mapped[str | None] = mapped_column(Text)
  response_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON)
  status: Mapped[str | None] = mapped_column(String(50))
  error_message: Mapped[str | None] = mapped_column(Text)
  collected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class LawDocument(Base):
  __tablename__ = "law_documents"
  __table_args__ = (
    UniqueConstraint("law_id", "effective_date", "article_no", "paragraph_no", name="uq_law_documents_article"),
    Index("idx_law_documents_law_name", "law_name"), Index("idx_law_documents_effective_date", "effective_date"),
    Index("idx_law_documents_article_no", "article_no"),
    Index("idx_law_documents_metadata", "metadata", postgresql_using="gin"),
  )

  id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
  parent_document_id: Mapped[int | None] = mapped_column(
    ID_TYPE, ForeignKey("law_documents.id"), nullable=True, index=True,
  )
  law_id: Mapped[str] = mapped_column(String(50), nullable=False)
  mst: Mapped[str | None] = mapped_column(String(50))
  law_name: Mapped[str] = mapped_column(String(255), nullable=False)
  law_type: Mapped[str | None] = mapped_column(String(50))
  ministry: Mapped[str | None] = mapped_column(String(100))
  article_no: Mapped[str] = mapped_column(String(50), nullable=False)
  article_title: Mapped[str | None] = mapped_column(String(255))
  paragraph_no: Mapped[str] = mapped_column(String(50), nullable=False, default="", server_default="")
  doc_type: Mapped[str] = mapped_column(String(50), nullable=False)
  content: Mapped[str] = mapped_column(Text, nullable=False)
  document_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)
  source_url: Mapped[str | None] = mapped_column(Text)
  effective_date: Mapped[date] = mapped_column(Date, nullable=False)
  parse_status: Mapped[str] = mapped_column(String(30), default="PARSED", server_default="PARSED", nullable=False)
  parse_error: Mapped[str | None] = mapped_column(Text)
  collected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
  updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class DailyLegalTermMapping(Base):
  __tablename__ = "daily_legal_term_mappings"
  __table_args__ = (
    UniqueConstraint("daily_term", "legal_term", "relation_type", name="uq_daily_legal_term_mapping"),
    Index("idx_daily_legal_term", "daily_term"), Index("idx_daily_legal_term_priority", "priority"),
  )

  id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
  daily_term: Mapped[str] = mapped_column(String(255), nullable=False)
  legal_term: Mapped[str] = mapped_column(String(255), nullable=False)
  relation_type: Mapped[str] = mapped_column(String(50), nullable=False, default="RELATED", server_default="RELATED")
  domain: Mapped[str | None] = mapped_column(String(100))
  priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
  raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
  created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
  updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
