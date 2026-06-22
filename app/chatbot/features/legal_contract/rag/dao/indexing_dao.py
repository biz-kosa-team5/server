from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..model import LawDocument


class DocumentIndexingDao:
  def __init__(self, session: Session):
    self.session = session

  def list_embedding_documents(self) -> list[LawDocument]:
    statement = select(LawDocument).order_by(LawDocument.id)
    return list(self.session.scalars(statement).all())

  def save_embedding(
    self,
    document_id: int,
    embedding: list[float],
    model: str,
    content_hash: str,
  ) -> None:
    row = self.session.get(LawDocument, document_id)
    if row is None:
      raise ValueError(f"Law document not found: {document_id}")
    row.embedding = embedding
    row.embedding_model = model
    row.embedding_status = "EMBEDDED"
    row.embedding_error = None
    row.embedding_content_hash = content_hash
    row.embedded_at = datetime.now(timezone.utc).replace(tzinfo=None)

  def mark_embeddings_failed(
    self,
    document_ids: list[int],
    model: str,
    content_hashes: list[str],
    error_message: str,
  ) -> None:
    rows = {
      row.id: row
      for row in self.session.scalars(
        select(LawDocument).where(LawDocument.id.in_(document_ids))
      ).all()
    }
    for document_id, content_hash in zip(document_ids, content_hashes, strict=True):
      row = rows.get(document_id)
      if row is None:
        continue
      row.embedding = None
      row.embedding_model = model
      row.embedding_status = "FAILED"
      row.embedding_error = error_message
      row.embedding_content_hash = content_hash
      row.embedded_at = None

  def embedding_status(self) -> dict[str, Any]:
    total = self.session.scalar(select(func.count()).select_from(LawDocument)) or 0
    with_embedding = self.session.scalar(
      select(func.count()).select_from(LawDocument)
      .where(LawDocument.embedding.is_not(None))
    ) or 0
    status_rows = self.session.execute(
      select(LawDocument.embedding_status, func.count())
      .group_by(LawDocument.embedding_status)
      .order_by(LawDocument.embedding_status)
    ).all()
    return {
      "total": total,
      "withEmbedding": with_embedding,
      "withoutEmbedding": total - with_embedding,
      "statuses": [
        {"status": status or "UNKNOWN", "count": count}
        for status, count in status_rows
      ],
    }

  def commit(self) -> None:
    self.session.commit()

  def rollback(self) -> None:
    self.session.rollback()
