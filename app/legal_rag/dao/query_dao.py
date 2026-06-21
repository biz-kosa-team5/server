from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..model import DailyLegalTermMapping, LawDocument


@dataclass(frozen=True)
class RankedLawDocument:
  document: LawDocument
  score: float


class LegalRagQueryDao:
  def __init__(self, session: Session):
    self.session = session

  def matching_term_mappings(self, question: str) -> list[DailyLegalTermMapping]:
    normalized_question = question.lower()
    rows = self.session.scalars(
      select(DailyLegalTermMapping)
      .order_by(DailyLegalTermMapping.priority.desc(), DailyLegalTermMapping.id)
    ).all()
    return [
      row
      for row in rows
      if row.daily_term and row.daily_term.lower() in normalized_question
    ]

  def list_embedded_law_documents(self) -> list[LawDocument]:
    return list(self.session.scalars(
      select(LawDocument)
      .where(LawDocument.embedding.is_not(None))
      .order_by(LawDocument.id)
    ).all())

  def nearest_law_documents(
    self,
    query_embedding: list[float],
    top_k: int,
  ) -> list[RankedLawDocument] | None:
    if self.session.get_bind().dialect.name != "postgresql":
      return None

    distance = LawDocument.embedding.cosine_distance(query_embedding).label("distance")
    rows = self.session.execute(
      select(LawDocument, distance)
      .where(LawDocument.embedding.is_not(None))
      .order_by(distance)
      .limit(top_k)
    ).all()
    return [
      RankedLawDocument(document=row[0], score=max(0.0, 1.0 - float(row[1])))
      for row in rows
    ]
