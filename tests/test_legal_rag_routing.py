from app.main import app


def test_legal_rag_routes_are_grouped_by_pipeline():
  paths = app.openapi()["paths"]

  assert paths["/api/laws/ingest/raw"]["post"]["tags"] == ["legal-rag-ingestion"]
  assert paths["/api/laws/parse"]["post"]["tags"] == ["legal-rag-ingestion"]
  assert paths["/api/laws/embeddings"]["post"]["tags"] == ["legal-rag-indexing"]
  assert paths["/api/laws/embeddings/status"]["get"]["tags"] == ["legal-rag-indexing"]
