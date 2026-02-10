# Step 4 실행 산출물

## 목적
operators/datasets/data-fields 메타데이터를 API에서 수집해 JSON + SQLite로 유지한다.

## 완료 범위
- API 수집:
  - `src/brain_agent/brain_api/metadata.py`
    - `get_operators`
    - `get_datasets` (limit/offset pagination)
    - `get_data_fields` (dataset.id/type/search + pagination)
- 저장 스키마(SQLite):
  - `src/brain_agent/storage/sqlite_store.py`
    - `operators`, `datasets`, `data_fields` 테이블 생성/업서트
- 동기화 워크플로:
  - `src/brain_agent/metadata/sync.py`
    - `sync_operators`, `sync_datasets`, `sync_data_fields`, `sync_all_metadata`
  - 실행 스크립트: `scripts/sync_metadata.sh`
- 동기화 정책 구조화:
  - `src/brain_agent/config.py` (`MetadataSyncPolicy`)

## Step 5+ 인계 메모
- Step 5 retrieval은 본 단계 SQLite 저장소(`data/brain_agent.db`)를 검색 소스로 사용한다.
