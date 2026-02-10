# Step 1 실행 산출물

## 목적
`docs/steps/step-01.md`의 3개 항목(추천 스택, WSL 프로젝트 폴더 생성, requirements 템플릿)을 재현 가능한 형태로 고정한다.

## 1.1 추천 스택 확정
- Python: 3.11+
- 기본 패키지:
  - requests
  - pydantic
  - pandas
  - tenacity
  - python-dotenv
  - rich
- 선택 패키지:
  - aiohttp 또는 httpx
  - duckdb
  - faiss 또는 rank-bm25

## 1.2 WSL 프로젝트 폴더 생성 절차 고정
- 표준 경로: `~/wqbrain-agent`
- 실행 스크립트: `docs/artifacts/step-01/bootstrap_wsl.sh`
- 사용 방법:
  - `bash docs/artifacts/step-01/bootstrap_wsl.sh`
  - 경로를 변경할 경우: `bash docs/artifacts/step-01/bootstrap_wsl.sh /custom/path/wqbrain-agent`

## 1.3 requirements 템플릿 고정
- 템플릿 파일: `docs/artifacts/step-01/requirements.txt`
- 적용 예시:
  - `cp docs/artifacts/step-01/requirements.txt ~/wqbrain-agent/requirements.txt`

## Step 2+ 인계 메모
- Step 2 시작 전 `.venv` 활성화와 `requirements.txt` 설치를 먼저 수행한다.
- Step 2의 인증/세션 구현(`docs/steps/step-02.md`)은 본 단계의 Python 3.11+와 기본 패키지 구성을 전제한다.
