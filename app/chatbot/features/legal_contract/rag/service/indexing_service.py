from __future__ import annotations

import hashlib

from app.chatbot.embedding import EmbeddingClient

from ..dao import DocumentIndexingDao
from ..model import LawDocument


class DocumentEmbeddingService:
  def __init__(self, dao: DocumentIndexingDao, client: EmbeddingClient):
    self.dao = dao
    self.client = client

  def embed_documents(
    self,
    batch_size: int = 100,
    retry_failed: bool = False,
    limit: int | None = None,
  ) -> dict[str, int | str]:
    candidates: list[tuple[LawDocument, str, str]] = []
    skipped = 0
    for document in self.dao.list_embedding_documents():
      text = self.client.prepare_text(build_embedding_text(document))
      content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
      unchanged = (
        document.embedding is not None
        and document.embedding_model == self.client.model
        and document.embedding_content_hash == content_hash
        and document.embedding_status == "EMBEDDED"
      )
      failed_without_changes = (
        document.embedding_status == "FAILED"
        and document.embedding_model == self.client.model
        and document.embedding_content_hash == content_hash
      )
      if unchanged or (failed_without_changes and not retry_failed):
        skipped += 1
        continue
      candidates.append((document, text, content_hash))
      if limit is not None and len(candidates) >= limit:
        break

    embedded = 0
    failed = 0
    for start in range(0, len(candidates), batch_size):
      batch = candidates[start:start + batch_size]
      ids = [document.id for document, _, _ in batch]
      try:
        vectors = self.client.embed([text for _, text, _ in batch])
        for (document, _, content_hash), vector in zip(batch, vectors, strict=True):
          self.dao.save_embedding(
            document.id,
            vector,
            self.client.model,
            content_hash,
          )
        self.dao.commit()
        embedded += len(batch)
      except Exception as error:
        self.dao.rollback()
        self.dao.mark_embeddings_failed(
          ids,
          self.client.model,
          [content_hash for _, _, content_hash in batch],
          str(error)[:4000],
        )
        self.dao.commit()
        failed += len(batch)

    return {
      "candidates": len(candidates),
      "embedded": embedded,
      "failed": failed,
      "skipped": skipped,
      "model": self.client.model,
      "dimensions": self.client.dimensions,
    }


def build_embedding_text(document: LawDocument) -> str:
  return "\n".join([
    f"법령명: {document.law_name}",
    f"법령구분: {document.law_type or ''}",
    f"조문: {document.article_no}",
    f"조문제목: {document.article_title or ''}",
    "내용:",
    document.content,
  ])
