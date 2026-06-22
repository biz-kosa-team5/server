from datetime import date

from app.database import SessionLocal, initialize_database
from app.chatbot.features.legal_contract.rag.dao import DocumentIndexingDao
from app.chatbot.features.legal_contract.rag.model import LawDocument
from app.chatbot.features.legal_contract.rag.service.indexing_service import DocumentEmbeddingService, build_embedding_text


class FakeEmbeddingClient:
  model = "text-embedding-3-large"
  dimensions = 1536

  def prepare_text(self, text: str) -> str:
    return text

  def embed(self, texts: list[str]) -> list[list[float]]:
    return [[0.1] * self.dimensions for _ in texts]


def test_embedding_service_saves_vector_and_skips_unchanged_document():
  initialize_database()
  with SessionLocal() as session:
    document = LawDocument(
      law_id="EMBED-TEST",
      law_name="테스트법",
      law_type="법률",
      ministry="법무부",
      article_no="제1조",
      article_title="목적",
      paragraph_no="",
      doc_type="article",
      content="임베딩 테스트 본문",
      effective_date=date(2026, 6, 19),
    )
    session.add(document)
    session.commit()

    service = DocumentEmbeddingService(DocumentIndexingDao(session), FakeEmbeddingClient())
    first = service.embed_documents(batch_size=10)
    second = service.embed_documents(batch_size=10)

    session.refresh(document)
    assert first["embedded"] == 1
    assert first["failed"] == 0
    assert second["candidates"] == 0
    assert second["skipped"] == 1
    assert document.embedding_status == "EMBEDDED"
    assert document.embedding_model == "text-embedding-3-large"
    assert len(document.embedding) == 1536
    assert len(document.embedding_content_hash) == 64


def test_embedding_text_matches_legal_rag_plan_format():
  document = LawDocument(
    law_id="FORMAT-TEST",
    law_name="민법",
    law_type="법률",
    ministry="법무부",
    article_no="제565조",
    article_title="해약금",
    paragraph_no="",
    doc_type="article",
    content="계약금에 관한 내용",
    effective_date=date(2026, 6, 19),
  )

  assert build_embedding_text(document) == (
    "법령명: 민법\n"
    "법령구분: 법률\n"
    "조문: 제565조\n"
    "조문제목: 해약금\n"
    "내용:\n"
    "계약금에 관한 내용"
  )
