# Step 1

## WSL(Windows) 개발 환경 세팅


### 1.1 추천 스택
- Python 3.11+ (wqb도 3.11+ 권장)
- 패키지(권장):
  - requests (기본 API)
  - pydantic (스키마/검증)
  - pandas (레코드셋 처리)
  - tenacity (재시도/backoff)
  - rich 또는 loguru (로그)
  - sqlite3/duckdb (로컬 저장)
  - (선택) aiohttp/httpx (비동기)
  - (선택) faiss / rank-bm25 (메타데이터 검색)

### 1.2 WSL에서 프로젝트 폴더 생성
```bash
# WSL Ubuntu 예시
mkdir -p ~/wqbrain-agent
cd ~/wqbrain-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip wheel setuptools
````

### 1.3 requirements.txt 예시

```txt
requests>=2.31
pydantic>=2.6
pandas>=2.1
tenacity>=8.2
python-dotenv>=1.0
rich>=13.7
```

---


## 체크리스트
- [ ] 추천 스택
- [ ] WSL에서 프로젝트 폴더 생성
- [ ] requirements.txt 예시
- [ ] 이 단계 산출물을 저장하고 후속 단계 의존성을 기록했다.
