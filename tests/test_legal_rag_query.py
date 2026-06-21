from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.legal_rag.dao import LegalRagQueryDao
from app.legal_rag.model import DailyLegalTermMapping, LawDocument
from app.legal_rag.service.query import LegalRagQueryService, build_query_embedding_text
from app.models import Base


class FakeEmbeddingClient:
  model = "fake-embedding"
  dimensions = 1536

  def __init__(self, vector: list[float]):
    self.vector = vector
    self.texts: list[str] = []

  def prepare_text(self, text: str) -> str:
    return text

  def embed(self, texts: list[str]) -> list[list[float]]:
    self.texts.extend(texts)
    return [self.vector for _ in texts]


def make_session():
  engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    future=True,
  )
  Base.metadata.create_all(bind=engine)
  session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
  return session_factory()


def vector_at(index: int) -> list[float]:
  vector = [0.0] * FakeEmbeddingClient.dimensions
  vector[index] = 1.0
  return vector


def add_law_document(session, embedding: list[float]) -> LawDocument:
  document = LawDocument(
    law_id="QUERY-TEST",
    law_name="민법",
    law_type="법률",
    ministry="법무부",
    article_no="제565조",
    article_title="해약금",
    paragraph_no="",
    doc_type="article",
    content="계약금 해제에 관한 내용",
    effective_date=date(2026, 6, 19),
    embedding=embedding,
    embedding_model="fake-embedding",
    embedding_status="EMBEDDED",
  )
  session.add(document)
  session.commit()
  return document


def test_query_embedding_text_matches_plan_format():
  assert build_query_embedding_text("계약금 돌려받을 수 있어?", ["해약금"]) == (
    "사용자 질문: 계약금 돌려받을 수 있어?\n"
    "검색 확장어: 해약금"
  )


def test_query_uses_daily_term_mapping_and_python_cosine_fallback():
  with make_session() as session:
    session.add(DailyLegalTermMapping(
      daily_term="계약금",
      legal_term="해약금",
      relation_type="RELATED",
      priority=10,
    ))
    add_law_document(session, vector_at(0))
    client = FakeEmbeddingClient(vector_at(0))

    result = LegalRagQueryService(LegalRagQueryDao(session), client).query("계약금 돌려받을 수 있어?")

  assert result["success"] is True
  assert result["expandedTerms"] == ["해약금"]
  assert result["sources"][0]["lawName"] == "민법"
  assert result["sources"][0]["score"] == 1.0
  assert "검색 확장어: 해약금" in client.texts[0]


def test_query_returns_no_legal_sources_without_embedded_documents():
  with make_session() as session:
    result = LegalRagQueryService(
      LegalRagQueryDao(session),
      FakeEmbeddingClient(vector_at(0)),
    ).query("계약서 확인할 조항 알려줘")

  assert result["success"] is False
  assert result["reason"] == "no_legal_sources"
  assert result["sources"] == []


def test_query_returns_no_legal_sources_when_similarity_is_below_threshold():
  with make_session() as session:
    add_law_document(session, vector_at(1))

    result = LegalRagQueryService(
      LegalRagQueryDao(session),
      FakeEmbeddingClient(vector_at(0)),
    ).query("계약서 확인할 조항 알려줘")

  assert result["success"] is False
  assert result["reason"] == "no_legal_sources"


def test_query_returns_embedding_unavailable_without_openai_key(monkeypatch):
  monkeypatch.delenv("OPENAI_API_KEY", raising=False)
  with make_session() as session:
    result = LegalRagQueryService(LegalRagQueryDao(session)).query("계약서 확인할 조항 알려줘")

  assert result["success"] is False
  assert result["reason"] == "embedding_unavailable"
