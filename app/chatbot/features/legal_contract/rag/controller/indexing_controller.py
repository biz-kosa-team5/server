from fastapi import APIRouter

from ..dao import DocumentIndexingDao
from ..dto.indexing import (
  EmbeddingRequest,
  EmbeddingStatusResponse,
  EmbeddingSummary,
)
from .dependencies import DocumentEmbeddingServiceDep, SessionDep


router = APIRouter(tags=["legal-rag-indexing"])


@router.post("/api/laws/embeddings", response_model=EmbeddingSummary)
def embed_law_documents(
  request: EmbeddingRequest,
  service: DocumentEmbeddingServiceDep,
):
  return service.embed_documents(
    batch_size=request.batch_size,
    retry_failed=request.retry_failed,
    limit=request.limit,
  )


@router.get("/api/laws/embeddings/status", response_model=EmbeddingStatusResponse)
def embedding_status(session: SessionDep):
  return DocumentIndexingDao(session).embedding_status()
