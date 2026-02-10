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

2. 크리덴셜 설정 (권장: `.env`)
```bash
cp .env.example .env
# .env 파일에 BRAIN_CREDENTIAL_EMAIL / BRAIN_CREDENTIAL_PASSWORD 입력
```

3. (대안) 홈 디렉토리 크리덴셜 파일 생성
```bash
bash scripts/setup_credentials.sh
```

4. 시뮬레이션 옵션 동기화
```bash
PYTHONPATH=src bash scripts/sync_options.sh
```

5. 메타데이터 동기화
```bash
PYTHONPATH=src bash scripts/sync_metadata.sh --region USA --delay 1 --universe TOP3000
```

> biometrics 인증이 필요한 계정이면 위 스크립트가 URL을 안내하고 터미널에서 대기합니다.
> 브라우저에서 인증 완료 후 Enter를 누르면 진행됩니다.
> 세션 쿠키(`~/.brain_session_cookies`)를 재사용하므로 연속 실행 시 재인증이 줄어듭니다.
> 참고로 `sync_metadata.sh`는 내부적으로 options 동기화도 함께 수행합니다.

## 인증 우선순위

CLI 실행 시 자격증명은 아래 순서로 로드됩니다.
1. 환경변수: `BRAIN_CREDENTIAL_EMAIL`, `BRAIN_CREDENTIAL_PASSWORD` (`.env` 포함)
2. 호환 환경변수: `BRAIN_EMAIL`, `BRAIN_PASSWORD`
3. 파일: `~/.brain_credentials` (또는 `--credentials`로 지정한 경로)

비대화형 실행(예: cron)에서 biometrics 대기를 비활성화하려면:
```bash
BRAIN_INTERACTIVE_LOGIN=0 PYTHONPATH=src bash scripts/sync_options.sh
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

## 샘플 Fixture

- API 응답 샘플(JSON): `docs/artifacts/fixtures/`
- 예시 목적이며, 운영 시에는 실제 API fetch 결과를 사용하세요.

## 주의

- 실제 로그인/바이오메트릭 인증은 사용자 수동 개입이 필요할 수 있습니다.
- submit endpoint는 계정 권한/정책에 따라 동작이 다를 수 있어 옵션으로 분리했습니다.
