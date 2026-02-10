# Step 5 실행 산출물

## 목적
LLM 컨텍스트를 줄이기 위해 metadata retrieval 기반 지식베이스 계층을 구축한다.

## 완료 범위
- 간단 버전(BM25/키워드):
  - `src/brain_agent/retrieval/keyword.py`
  - operators/fields/datasets Top-K 검색 API 구현
- 고급 버전(옵션 임베딩):
  - `src/brain_agent/retrieval/embedding.py`
  - FAISS + sentence-transformers 기반 인덱스/검색 구현(옵션 의존성)
- 예시 입력:
  - `docs/artifacts/step-05/retrieval_query.example.json`

## Step 6+ 인계 메모
- Step 6 정적검증과 결합할 때 retrieval 결과 subset만 LLM/생성기로 전달해 실패율/비용을 낮춘다.
