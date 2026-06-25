from __future__ import annotations

from .query_intent import LegalQueryIntent
from .query_text import unique_terms


INTENT_EXPANSION_TERMS = {
  LegalQueryIntent.TAX: [
    "취득세",
    "양도소득세",
    "증여세",
    "과세표준",
    "세율",
  ],
  LegalQueryIntent.CONTRACT: [
    "매매의 의의",
    "대금 지급",
    "계약금",
    "계약 해제",
    "해약금",
  ],
  LegalQueryIntent.CHECKLIST: [
    "거래계약서의 작성",
    "거래가액과 매매목록",
    "계약금",
    "해약금",
    "중개대상물 확인 설명",
    "저당권",
  ],
  LegalQueryIntent.PRE_CONTRACT_CHECK: [
    "중개대상물 확인 설명",
    "권리관계",
    "등기사항증명서",
    "거래 또는 이용 제한",
    "저당권",
    "근저당권",
    "전세권",
    "임차권",
    "대항력",
    "부동산 거래의 신고",
  ],
  LegalQueryIntent.REGISTRATION: [
    "소유권 이전등기",
    "소유권 이전",
    "등기신청",
    "등기원인",
    "권리 이전",
  ],
  LegalQueryIntent.LEASE: [
    "임대차",
    "임차인",
    "대항력",
    "주택의 인도",
    "주민등록",
    "임차주택의 양수인",
    "임대인의 지위 승계",
    "보증금",
    "보증금 반환",
    "우선변제권",
    "임차권등기",
  ],
  LegalQueryIntent.BROKER: [
    "공인중개사",
    "거래계약서",
    "설명의무",
    "거짓 기재",
  ],
  LegalQueryIntent.RISK: [
    "처분의 제한",
    "가등기",
    "저당권",
    "근저당권",
    "압류",
    "가압류",
    "가처분",
    "경매개시결정",
    "전세권",
    "임차권등기",
    "갑구",
    "을구",
    "접수번호",
    "순위번호",
    "채권최고액",
  ],
  LegalQueryIntent.FALSE_PRICE: [
    "실제 거래가격",
    "거짓 신고",
    "거래금액 거짓 기재",
    "서로 다른 둘 이상의 거래계약서",
    "부동산 거래의 신고",
    "거래계약신고필증",
    "양도소득세 비과세 감면 배제",
  ],
}

BROAD_EXPANSION_TERMS = [
  "매매계약",
  "부동산 거래의 신고",
  "거래계약서의 작성",
  "거래가액과 매매목록",
  "소유권 이전등기",
  "취득세",
  "양도소득세",
  "공인중개사",
  "중개대상물 확인 설명",
  "권리관계",
  "등기사항증명서",
  "대항력",
  "저당권",
  "근저당권",
  "압류",
  "가압류",
]


def build_intent_expansion_terms(intents: list[LegalQueryIntent]) -> list[str]:
  terms: list[str] = []
  if LegalQueryIntent.BROAD in intents:
    terms.extend(BROAD_EXPANSION_TERMS)
  for intent in intents:
    terms.extend(INTENT_EXPANSION_TERMS.get(intent, []))
  return unique_terms(terms)
