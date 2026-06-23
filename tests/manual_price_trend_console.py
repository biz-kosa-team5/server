"""자연어 질문부터 시세추이 응답까지 콘솔에서 확인하는 수동 테스트."""

from __future__ import annotations

import json

from app.chatbot.features.price_trend import (
    extract_price_trend_slots,
    run_price_trend,
)
from app.database import SessionLocal, ensure_initialized


def print_json(title: str, value: dict) -> None:
    print(f"\n[{title}]")
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main() -> None:
    ensure_initialized()

    print("시세추이 질문을 입력하세요.")
    print("예: 파크리오 34평 최근 3년 시세 추이 알려줘")
    print("종료하려면 빈 줄을 입력하세요.")

    with SessionLocal() as session:
        while True:
            question = input("\n질문> ").strip()
            if not question:
                break

            slots = extract_price_trend_slots(question)
            print_json("추출된 슬롯", slots)

            result = run_price_trend(session, slots, question)
            print_json("최종 응답", result)


if __name__ == "__main__":
    main()
