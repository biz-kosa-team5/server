# LLM 기반 챗봇 처리 흐름

```mermaid
flowchart TD
  A[사용자 질문] --> B[질문 정리<br/>conversation_memory.py<br/>splitter.py<br/>planner.py]
  B --> C[LLM Supervisor<br/>supervisor.py]

  C --> D{전문 Agent 선택<br/>단일 또는 복수 선택}

  D --> A1[조회 Agent]
  D --> A2[추천 Agent]
  D --> A3[비교 Agent]
  D --> A4[시세 Agent]
  D --> A5[법령 Agent]

  A1 --> T1[simple_lookup Tool]
  A2 --> T2[recommend_apartments Tool]
  A3 --> T3[compare_apartments Tool]
  A4 --> T4[analyze_price_trend Tool]
  A5 --> T5[search_legal_contract Tool]

  T1 --> F[구조화된 조회 결과]
  T2 --> F
  T3 --> F
  T4 --> F
  T5 --> F

  F --> G[구조화 결과 취합]
  G --> V{결과 보정 필요?}

  V -- 추천 후 비교 보정 --> R1[추천 후보 기준 비교 재실행<br/>chatbot_service.py]
  V -- 중복 조회 제거 --> R2[비교 성공 시 lookup 결과 정리<br/>chatbot_service.py]
  V -- Tool 선택 실패/오선택 --> R3[Direct Fallback<br/>chatbot_service.py]
  V -- 보정 불필요 --> P[결과 정리<br/>chatbot_service.py]

  R1 --> P
  R2 --> P
  R3 --> P

  P --> H[화면 표시 데이터 생성<br/>ui_payload.py]
  P --> I[최종 답변 생성<br/>answer/composer.py]

  H --> J[응답]
  I --> J

  C -. 예외 .-> R3
  D -. 여러 Agent 선택 .-> A1
  D -. 여러 Agent 선택 .-> A2
  D -. 여러 Agent 선택 .-> A3
```

## 요약

- 기본 실행 흐름은 `LLM Supervisor -> 전문 Agent -> 전문 Tool` 구조다.
- 질문 정리 단계에서는 대화 맥락 정리, 질문 분리, task 단위 계획을 만든다.
- Supervisor는 질문에 따라 단일 Agent 또는 여러 Agent를 선택할 수 있다.
- Agent는 도메인별 Tool을 호출하고, Tool은 DB/RAG/service 결과를 구조화된 JSON으로 반환한다.
- `chatbot_service.py`는 추천 후 비교 보정, 중복 lookup 제거, direct fallback 같은 결과 정리를 담당한다.
- `ui_payload.py`는 화면 표시 데이터, `answer/composer.py`는 최종 답변 생성을 담당한다.
