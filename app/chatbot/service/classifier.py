from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache

from ..embedding import (
  DEFAULT_SENTENCE_TRANSFORMER_MODEL,
  EmbeddingClient,
  SentenceTransformerEmbeddingClient,
  top_k_nearest_neighbors,
)
from ..types import Intent


LEGAL_KEYWORDS = ("법률", "계약", "매매 시", "확인할 사항", "세금", "등기")
COMPARISON_KEYWORDS = ("비교", "둘 중", "어디가 더", "더 신축", "더 싸")
TREND_KEYWORDS = ("추이", "올랐", "떨어졌", "많이 오른", "변화")
LOOKUP_KEYWORDS = ("어디", "위치", "얼마", "최근 실거래", "최고가")
RECOMMENDATION_KEYWORDS = ("추천", "근처", "예산", "세대", "신축", "초등학교", "초중고", "가까이", "가까운", "싼 곳", "찾아줘")
DEFAULT_INTENT_CLASSIFIER = "keyword"
DEFAULT_INTENT_K = 3
DEFAULT_INTENT_THRESHOLD = 0.55

INTENT_REFERENCE_SENTENCES: dict[Intent, tuple[str, ...]] = {
  Intent.SIMPLE_LOOKUP: (
    "아파트 위치가 어디인지 알려줘",
    "최근 실거래가가 얼마인지 알려줘",
    "단지 주소와 기본 정보를 찾아줘",
    "최고가 거래가 얼마인지 알려줘",
  ),
  Intent.RECOMMENDATION: (
    "예산에 맞는 아파트를 추천해줘",
    "역 근처 신축 아파트를 찾아줘",
    "초등학교 가까운 단지를 추천해줘",
    "세대수가 많은 아파트를 보여줘",
  ),
  Intent.COMPARISON: (
    "두 아파트 가격을 비교해줘",
    "둘 중 어디가 더 싼지 알려줘",
    "단지별 평형과 가격을 비교해줘",
    "어느 아파트가 더 신축인지 비교해줘",
  ),
  Intent.PRICE_TREND: (
    "최근 가격 추이를 알려줘",
    "많이 오른 아파트를 찾아줘",
    "실거래가가 어떻게 변했는지 보여줘",
    "가격이 떨어진 단지를 알려줘",
  ),
  Intent.LEGAL_CONTRACT: (
    "매매 계약 시 확인할 법률을 알려줘",
    "등기와 세금에서 주의할 점을 알려줘",
    "부동산 계약서에서 확인할 사항을 알려줘",
    "계약금과 해약금 관련 법률을 찾아줘",
  ),
}


@dataclass(frozen=True)
class IntentClassification:
  intent: Intent
  confidence: float | None = None


class KeywordIntentClassifier:
  def classify(self, question: str) -> IntentClassification:
    text = question.strip()
    if not text:
      return IntentClassification(Intent.UNSUPPORTED)

    if _contains_any(text, LEGAL_KEYWORDS):
      return IntentClassification(Intent.LEGAL_CONTRACT)
    if _contains_any(text, COMPARISON_KEYWORDS):
      return IntentClassification(Intent.COMPARISON)
    if _contains_any(text, TREND_KEYWORDS):
      return IntentClassification(Intent.PRICE_TREND)
    if _contains_any(text, LOOKUP_KEYWORDS):
      return IntentClassification(Intent.SIMPLE_LOOKUP)
    if _contains_any(text, RECOMMENDATION_KEYWORDS):
      return IntentClassification(Intent.RECOMMENDATION)
    return IntentClassification(Intent.UNSUPPORTED)


class EmbeddingIntentClassifier:
  def __init__(
    self,
    client: EmbeddingClient,
    reference_sentences: dict[Intent, tuple[str, ...]] | None = None,
    k: int = DEFAULT_INTENT_K,
    threshold: float = DEFAULT_INTENT_THRESHOLD,
  ):
    self.client = client
    self.reference_sentences = reference_sentences or INTENT_REFERENCE_SENTENCES
    self.k = k
    self.threshold = threshold
    self._references = [
      (intent, sentence)
      for intent, sentences in self.reference_sentences.items()
      for sentence in sentences
    ]
    prepared = [self.client.prepare_text(sentence) for _, sentence in self._references]
    self._reference_vectors = self.client.embed(prepared)

  def classify(self, question: str) -> IntentClassification:
    text = question.strip()
    if not text:
      return IntentClassification(Intent.UNSUPPORTED, 0.0)

    if not self._references or not self._reference_vectors:
      return IntentClassification(Intent.UNSUPPORTED, 0.0)

    query_vector = self.client.embed([self.client.prepare_text(text)])[0]
    neighbors = top_k_nearest_neighbors(
      query_vector,
      self._reference_vectors,
      min(self.k, len(self._reference_vectors)),
    )
    if not neighbors:
      return IntentClassification(Intent.UNSUPPORTED, 0.0)

    scores_by_intent: dict[Intent, list[float]] = defaultdict(list)
    for neighbor in neighbors:
      intent, _ = self._references[neighbor.index]
      scores_by_intent[intent].append(neighbor.score)

    best_intent, best_scores = sorted(
      scores_by_intent.items(),
      key=lambda item: (
        -len(item[1]),
        -max(item[1]),
        -(sum(item[1]) / len(item[1])),
        item[0].value,
      ),
    )[0]
    confidence = max(best_scores)
    if confidence < self.threshold:
      return IntentClassification(Intent.UNSUPPORTED, confidence)
    return IntentClassification(best_intent, confidence)


def classify_intent(question: str) -> Intent:
  return classify_intent_with_confidence(question).intent


def classify_intent_with_confidence(question: str) -> IntentClassification:
  return get_intent_classifier().classify(question)


def get_intent_classifier() -> KeywordIntentClassifier | EmbeddingIntentClassifier:
  classifier = os.getenv("CHATBOT_INTENT_CLASSIFIER", DEFAULT_INTENT_CLASSIFIER)
  classifier = classifier.strip().lower()
  model = os.getenv("CHATBOT_INTENT_EMBEDDING_MODEL", DEFAULT_SENTENCE_TRANSFORMER_MODEL)
  k = int(os.getenv("CHATBOT_INTENT_K", str(DEFAULT_INTENT_K)))
  threshold = float(os.getenv("CHATBOT_INTENT_THRESHOLD", str(DEFAULT_INTENT_THRESHOLD)))
  return _build_intent_classifier(classifier, model, k, threshold)


@lru_cache(maxsize=8)
def _build_intent_classifier(
  classifier: str,
  model: str,
  k: int,
  threshold: float,
) -> KeywordIntentClassifier | EmbeddingIntentClassifier:
  if classifier == "keyword":
    return KeywordIntentClassifier()
  if classifier == "embedding":
    return EmbeddingIntentClassifier(
      SentenceTransformerEmbeddingClient(model=model),
      k=k,
      threshold=threshold,
    )
  raise ValueError(f"Unsupported CHATBOT_INTENT_CLASSIFIER: {classifier}")


def clear_intent_classifier_cache() -> None:
  _build_intent_classifier.cache_clear()


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
  return any(keyword in text for keyword in keywords)
