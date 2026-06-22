import json
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.chatbot.features.legal_contract.normalization import normalize_query
from app.chatbot.features.legal_contract.rag.dao import LegalRagQueryDao
from app.chatbot.features.legal_contract.rag.model import DailyLegalTermMapping, LawDocument
from app.chatbot.features.legal_contract.rag.service.query_service import (
  LegalRagQueryService,
  build_query_embedding_text,
  extract_query_terms,
  longest_terms,
)
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


def test_normalize_query_keeps_meaning_and_normalizes_text_format():
  question = "  CONTRACT\t계약금을...\n돌려받을 수 있나요??  "

  assert normalize_query(question) == "contract 계약금을 돌려받을 수 있나요"


def test_normalize_query_converts_decomposed_hangul_to_nfc():
  decomposed_question = "계약금"

  assert normalize_query(decomposed_question) == "계약금"


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


def add_rankable_law_document(
  session,
  law_id: str,
  law_name: str,
  article_title: str,
  content: str,
  embedding: list[float],
) -> LawDocument:
  document = LawDocument(
    law_id=law_id,
    law_name=law_name,
    law_type="법률",
    ministry="행정안전부",
    article_no="제1조",
    article_title=article_title,
    paragraph_no="",
    doc_type="article",
    content=content,
    effective_date=date(2026, 6, 22),
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


def test_extract_query_terms_keeps_legal_phrases_and_removes_particles():
  assert extract_query_terms(
    "아파트 매매계약서에서 소유권이전등기를 언제 신청해야 하나요",
  ) == ["아파트", "매매계약서", "소유권이전등기", "신청"]


def test_longest_terms_removes_shorter_contained_terms():
  assert longest_terms(["아파트", "계약", "계약금", "계약금"]) == ["아파트", "계약금"]


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


def test_query_uses_longest_matching_daily_term():
  with make_session() as session:
    session.add_all([
      DailyLegalTermMapping(
        daily_term="계약",
        legal_term="양도계약",
        relation_type="NARROWER",
        priority=70,
      ),
      DailyLegalTermMapping(
        daily_term="계약금",
        legal_term="해약금",
        relation_type="RELATED",
        priority=50,
      ),
    ])
    session.commit()

    mappings = LegalRagQueryDao(session).matching_term_mappings("계약금을 돌려받을 수 있나요")

  assert [(mapping.daily_term, mapping.legal_term) for mapping in mappings] == [
    ("계약금", "해약금"),
  ]


def test_query_reranks_vector_candidates_with_keyword_matches():
  with make_session() as session:
    session.add(DailyLegalTermMapping(
      daily_term="취득세",
      legal_term="취득세율",
      relation_type="RELATED",
      priority=50,
    ))
    session.commit()
    add_rankable_law_document(
      session,
      "WRONG-TAX",
      "종합부동산세법",
      "세율 및 세액",
      "주택 보유기간에 따른 세액 공제",
      [0.9, 0.435889894] + [0.0] * 1534,
    )
    correct = add_rankable_law_document(
      session,
      "ACQUISITION-TAX",
      "지방세법",
      "취득세율",
      "주택 취득세의 세율을 정한다",
      [0.8, 0.6] + [0.0] * 1534,
    )

    result = LegalRagQueryService(
      LegalRagQueryDao(session),
      FakeEmbeddingClient(vector_at(0)),
    ).query("아파트 취득세는 얼마인가요")

  assert result["sources"][0]["documentId"] == correct.id
  assert result["sources"][0]["vectorScore"] == 0.8
  assert result["sources"][0]["keywordScore"] > 0
  json.dumps(result)


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
