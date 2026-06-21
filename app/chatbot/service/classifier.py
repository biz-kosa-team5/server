from __future__ import annotations

from ..dto.chatbot_dto import Intent


LEGAL_KEYWORDS = ("법률", "계약", "매매 시", "확인할 사항", "세금", "등기")
COMPARISON_KEYWORDS = ("비교", "둘 중", "어디가 더", "더 신축", "더 싸")
TREND_KEYWORDS = ("추이", "올랐", "떨어졌", "많이 오른", "변화")
LOOKUP_KEYWORDS = ("어디", "위치", "얼마", "최근 실거래", "최고가")
RECOMMENDATION_KEYWORDS = ("추천", "근처", "예산", "세대", "신축", "초등학교", "싼 곳", "찾아줘")


def classify_intent(question: str) -> Intent:
  text = question.strip()
  if not text:
    return Intent.UNSUPPORTED

  if _contains_any(text, LEGAL_KEYWORDS):
    return Intent.LEGAL_CONTRACT
  if _contains_any(text, COMPARISON_KEYWORDS):
    return Intent.COMPARISON
  if _contains_any(text, TREND_KEYWORDS):
    return Intent.PRICE_TREND
  if _contains_any(text, LOOKUP_KEYWORDS):
    return Intent.SIMPLE_LOOKUP
  if _contains_any(text, RECOMMENDATION_KEYWORDS):
    return Intent.RECOMMENDATION
  return Intent.UNSUPPORTED


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
  return any(keyword in text for keyword in keywords)

