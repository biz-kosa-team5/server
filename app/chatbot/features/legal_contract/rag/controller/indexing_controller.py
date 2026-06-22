from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.chatbot.embedding import OpenAIEmbeddingClient

from app.database import get_session
from ..dao import DocumentIndexingDao
from ..dto.indexing import (
  EmbeddingRequest,
  EmbeddingStatusResponse,
  EmbeddingSummary,
)
from ..service.indexing import DocumentEmbeddingService


router = APIRouter(tags=["legal-rag-indexing"])


@router.post("/api/laws/embeddings", response_model=EmbeddingSummary)
def embed_law_documents(
  request: EmbeddingRequest,
  session: Session = Depends(get_session),
):
  service = DocumentEmbeddingService(
    DocumentIndexingDao(session),
    OpenAIEmbeddingClient(),
  )
  return service.embed_documents(
    batch_size=request.batch_size,
    retry_failed=request.retry_failed,
    limit=request.limit,
  )


@router.get("/api/laws/embeddings/status", response_model=EmbeddingStatusResponse)
def embedding_status(session: Session = Depends(get_session)):
  return DocumentIndexingDao(session).embedding_status()
