# Step 2 실행 산출물

## 목적
`docs/steps/step-02.md`의 인증/세션 초기화를 코드로 구현하고, 사용자 개입이 필요한 지점을 런타임 단계로 분리한다.

## 완료 범위
- 크리덴셜 로드/저장 구현:
  - `src/brain_agent/brain_api/client.py` (`load_credentials`, `save_credentials`)
  - `scripts/setup_credentials.sh`
  - `docs/artifacts/step-02/credentials.example.json`
- 자동 재로그인 세션 구현:
  - `BrainAPISession.ensure_login`
  - 200/204/401 처리 + 1회 재시도
  - persona biometrics 필요 시 `ManualActionRequired` 예외로 명시

## 사용자 개입 필요 항목
- 실제 계정 이메일/비밀번호 입력 및 `~/.brain_credentials` 생성
- 계정 정책상 biometrics가 활성화된 경우 브라우저 인증 수동 완료

## Step 3+ 인계 메모
- Step 3 실행 전 `scripts/setup_credentials.sh`로 크리덴셜 파일을 준비한다.
- 인증 성공 후 `scripts/sync_options.sh`부터 순차 실행한다.
