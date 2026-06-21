import pytest

from app.embeddings import cosine_similarity, top_k_nearest_neighbors
from app.embeddings import OpenAIEmbeddingClient as CommonOpenAIEmbeddingClient
from app.legal_rag.client import OpenAIEmbeddingClient as LegalRagOpenAIEmbeddingClient


def test_cosine_similarity_scores_and_top_k_neighbors_are_sorted():
  assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
  assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

  neighbors = top_k_nearest_neighbors(
    [1.0, 0.0],
    [
      [0.0, 1.0],
      [1.0, 0.0],
      [0.8, 0.2],
    ],
    k=2,
  )

  assert neighbors[0].index == 1
  assert neighbors[0].score == pytest.approx(1.0)
  assert neighbors[1].index == 2
  assert neighbors[1].score > 0.9


def test_embedding_similarity_handles_empty_inputs():
  assert cosine_similarity([], [1.0]) == 0.0
  assert cosine_similarity([1.0], []) == 0.0
  assert top_k_nearest_neighbors([1.0], [], k=3) == []
  assert top_k_nearest_neighbors([1.0], [[1.0]], k=0) == []


def test_cosine_similarity_rejects_dimension_mismatch():
  with pytest.raises(ValueError):
    cosine_similarity([1.0, 0.0], [1.0])


def test_legal_rag_openai_embedding_client_import_is_compatibility_shim():
  assert LegalRagOpenAIEmbeddingClient is CommonOpenAIEmbeddingClient
