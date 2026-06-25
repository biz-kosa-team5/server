from __future__ import annotations

from enum import StrEnum


class LegalQueryIntent(StrEnum):
  BROAD = "broad"
  TAX = "tax"
  CONTRACT = "contract"
  CHECKLIST = "checklist"
  PRE_CONTRACT_CHECK = "pre_contract_check"
  REGISTRATION = "registration"
  LEASE = "lease"
  BROKER = "broker"
  RISK = "risk"
  FALSE_PRICE = "false_price"
  GENERAL = "general"


INTENT_KEYWORDS = {
  LegalQueryIntent.TAX: (
    "세금", "세액", "세율", "과세", "취득세", "양도세", "양도소득세", "증여세",
  ),
  LegalQueryIntent.CONTRACT: (
    "계약", "계약금", "해제", "취소", "매매대금", "대금", "성립",
  ),
  LegalQueryIntent.CHECKLIST: (
    "계약서", "중요하게 볼", "중요한 부분", "확인할 부분", "체크", "주의할", "특약",
  ),
  LegalQueryIntent.PRE_CONTRACT_CHECK: (
    "계약 전", "계약 전에", "사기 전에", "살 때 확인", "꼭 확인", "법적 사항", "주의사항",
  ),
  LegalQueryIntent.REGISTRATION: (
    "명의", "이전등기", "소유권 이전", "등기", "신고필증",
  ),
  LegalQueryIntent.LEASE: (
    "세입자", "임차인", "임대차", "보증금", "전세", "전세 낀", "월세", "대항력",
    "보증금 누가", "보증금 돌려", "임대인 바뀌", "집주인 바뀌",
  ),
  LegalQueryIntent.BROKER: (
    "중개", "공인중개사", "중개사", "거래계약서", "설명 의무", "설명의무",
  ),
  LegalQueryIntent.RISK: (
    "빚", "근저당", "근저당 말고", "저당", "압류", "가압류", "가처분", "경매",
    "권리관계", "위험한 권리", "위험 권리", "등기부 위험", "등기부등본",
  ),
  LegalQueryIntent.FALSE_PRICE: (
    "실제보다 낮게", "낮게 계약서", "다운계약", "업계약", "허위 계약",
    "거짓 계약", "거래금액 거짓", "실제 거래가격",
  ),
}

BROAD_KEYWORDS = (
  "알아야 할",
  "알아야할",
  "중요하게 볼",
  "중요한 부분",
  "뭘 봐야",
  "무엇을 봐야",
  "집을 살 때",
  "집 살 때",
  "주의할",
  "유의할",
)


def detect_query_intents(question: str) -> list[LegalQueryIntent]:
  normalized = question.casefold()
  intents: list[LegalQueryIntent] = []

  for intent, keywords in INTENT_KEYWORDS.items():
    if any(keyword.casefold() in normalized for keyword in keywords):
      intents.append(intent)

  if should_add_broad_intent(normalized, intents):
    intents.insert(0, LegalQueryIntent.BROAD)

  if not intents:
    return [LegalQueryIntent.GENERAL]
  return list(dict.fromkeys(intents))


def should_add_broad_intent(
  normalized_question: str,
  specific_intents: list[LegalQueryIntent],
) -> bool:
  if not any(keyword in normalized_question for keyword in BROAD_KEYWORDS):
    return False
  # 권리관계/등기 위험처럼 이미 좁은 확인 대상이 있는 질문에는 broad 확장을 붙이지 않는다.
  if LegalQueryIntent.RISK in specific_intents:
    return False
  if (
    LegalQueryIntent.REGISTRATION in specific_intents
    and any(keyword in normalized_question for keyword in ("뭘 봐야", "무엇을 봐야", "확인"))
  ):
    return False
  return True


def has_intent(intents: list[LegalQueryIntent], intent: LegalQueryIntent) -> bool:
  return intent in intents
