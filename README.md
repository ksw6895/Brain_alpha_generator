# Brain Alpha Generator

WorldQuant BRAIN API 기반 알파 리서치/시뮬레이션 자동화 코드베이스입니다.

## 빠른 시작

1. 가상환경 구성
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

2. 크리덴셜 저장
```bash
bash scripts/setup_credentials.sh
```

3. 시뮬레이션 옵션 동기화
```bash
PYTHONPATH=src bash scripts/sync_options.sh
```

4. 메타데이터 동기화
```bash
PYTHONPATH=src bash scripts/sync_metadata.sh --region USA --delay 1 --universe TOP3000
```

## 주요 경로

- API 클라이언트: `src/brain_agent/brain_api/client.py`
- 메타데이터 동기화: `src/brain_agent/metadata/sync.py`
- 정적 검증기: `src/brain_agent/validation/static_validator.py`
- 시뮬레이션 러너: `src/brain_agent/simulation/runner.py`
- 평가기: `src/brain_agent/evaluation/evaluator.py`
- 피드백 변이기: `src/brain_agent/feedback/mutator.py`
- 파이프라인 오케스트레이터: `src/brain_agent/agents/pipeline.py`
- CLI 진입점: `src/brain_agent/cli.py`

## 주의

- 실제 로그인/바이오메트릭 인증은 사용자 수동 개입이 필요할 수 있습니다.
- submit endpoint는 계정 권한/정책에 따라 동작이 다를 수 있어 옵션으로 분리했습니다.
