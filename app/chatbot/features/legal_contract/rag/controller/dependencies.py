from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.chatbot.embedding import OpenAIEmbeddingClient
from app.database import get_session

from ..client import LawApiClient
from ..dao import DocumentIndexingDao, LegalDataDao, LegalRagQueryDao
from ..service.indexing_service import DocumentEmbeddingService
from ..service.ingestion_service import (
  LawCollectionService,
  LawParsingService,
  TermMappingCollectionService,
  TermMappingParsingService,
)
from ..service.query_service import LegalRagQueryService


SessionDep = Annotated[Session, Depends(get_session)]


def get_legal_rag_query_service(session: SessionDep) -> LegalRagQueryService:
  return LegalRagQueryService(LegalRagQueryDao(session))


def get_document_embedding_service(session: SessionDep) -> DocumentEmbeddingService:
  return DocumentEmbeddingService(
    DocumentIndexingDao(session),
    OpenAIEmbeddingClient(),
  )


def get_law_collection_service(session: SessionDep) -> LawCollectionService:
  return LawCollectionService(LegalDataDao(session), LawApiClient())


def get_law_parsing_service(session: SessionDep) -> LawParsingService:
  return LawParsingService(LegalDataDao(session))


def get_term_mapping_collection_service(session: SessionDep) -> TermMappingCollectionService:
  return TermMappingCollectionService(LegalDataDao(session), LawApiClient())


def get_term_mapping_parsing_service(session: SessionDep) -> TermMappingParsingService:
  return TermMappingParsingService(LegalDataDao(session))


LegalRagQueryServiceDep = Annotated[
  LegalRagQueryService,
  Depends(get_legal_rag_query_service),
]
DocumentEmbeddingServiceDep = Annotated[
  DocumentEmbeddingService,
  Depends(get_document_embedding_service),
]
LawCollectionServiceDep = Annotated[
  LawCollectionService,
  Depends(get_law_collection_service),
]
LawParsingServiceDep = Annotated[
  LawParsingService,
  Depends(get_law_parsing_service),
]
TermMappingCollectionServiceDep = Annotated[
  TermMappingCollectionService,
  Depends(get_term_mapping_collection_service),
]
TermMappingParsingServiceDep = Annotated[
  TermMappingParsingService,
  Depends(get_term_mapping_parsing_service),
]
