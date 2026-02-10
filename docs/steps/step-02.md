# Step 2

## Brain API “최초 사용” 단계 (인증/세션)


> 문서 1의 핵심: `/authentication`에 Basic Auth로 POST → 세션 쿠키(JWT)가 세팅됨.
> 이후 Session을 유지하면서 `/simulations`, `/alphas`, `/recordsets`를 호출.

### 2.1 크리덴셜 저장 (최소 방식: ~/.brain_credentials)

* WSL 홈: `/home/<user>/`
* 파일: `~/.brain_credentials`
* 내용(JSON): `["<email>", "<password>"]`
* 권한:

```bash
chmod 600 ~/.brain_credentials
```

### 2.2 BrainAPISession(권장 구현: “자동 재로그인” 포함)

#### 2.2.1 설계 요구사항

* `requests.Session()` 기반
* `POST /authentication`로 로그인
* `GET /authentication`로 로그인 상태/토큰 만료를 점검하고 필요 시 재로그인
* Biometrics(인증 앱/브라우저 확인) 흐름도 처리(문서 1 참고)

#### 2.2.2 코드 스켈레톤

```python
# src/brain_api/client.py
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
import requests
from urllib.parse import urljoin

API_BASE = "https://api.worldquantbrain.com"

@dataclass
class BrainCredentials:
    email: str
    password: str

def load_credentials(path: str | Path) -> BrainCredentials:
    p = Path(path).expanduser()
    raw = json.loads(p.read_text(encoding="utf-8"))
    return BrainCredentials(email=raw[0], password=raw[1])

class BrainAPISession:
    def __init__(self, creds: BrainCredentials, expiry_buffer_sec: int = 60):
        self.creds = creds
        self.expiry_buffer_sec = expiry_buffer_sec
        self.s = requests.Session()
        self.s.auth = (creds.email, creds.password)

    def auth_post(self) -> requests.Response:
        return self.s.post(f"{API_BASE}/authentication")

    def auth_get(self) -> requests.Response:
        return self.s.get(f"{API_BASE}/authentication")

    def ensure_login(self) -> None:
        """
        - 이미 로그인 상태면 OK
        - 만료 임박이면 재로그인
        - 204면 미로그인 → 로그인
        - 401 persona면 biometrics URL 안내 후 재시도
        """
        r = self.auth_get()
        if r.status_code == 200:
            payload = r.json()
            expiry = payload.get("token", {}).get("expiry", 0)
            if isinstance(expiry, (int, float)) and expiry > self.expiry_buffer_sec:
                return
            # 만료 임박 → 재로그인
            self._login_flow()
            return
        if r.status_code == 204:
            self._login_flow()
            return
        if r.status_code == 401:
            # 미인증/만료/정책 등
            self._login_flow()
            return
        # 기타: raise
        r.raise_for_status()

    def _login_flow(self) -> None:
        r = self.auth_post()
        if r.status_code == 201:
            return
        if r.status_code == 401:
            # biometrics sign-in enabled 인 경우 persona 헤더/Location 제공 가능
            if r.headers.get("WWW-Authenticate") == "persona" and "Location" in r.headers:
                url = urljoin(r.url, r.headers["Location"])
                print(f"[ACTION REQUIRED] Open this URL in a browser and complete biometrics:\n{url}")
                input("After completing biometrics, press Enter to continue...")
                # biometrics 완료 후 다시 POST
                r2 = self.s.post(url)
                r2.raise_for_status()
                return
            # reCAPTCHA required 등 (문서 1 참고) - 구현 옵션:
            raise RuntimeError(f"Unauthorized: {r.text}")
        r.raise_for_status()
```

---



## Step 2 실행 결과
- 산출물 문서: `docs/step-02-execution.md`
- 구현 산출물/완료 범위/의존성은 실행 문서에 정리.

## 체크리스트
- [x] 크리덴셜 저장 (최소 방식: ~/.brain_credentials)
- [x] BrainAPISession(권장 구현: “자동 재로그인” 포함)
- [x] 이 단계 산출물을 저장하고 후속 단계 의존성을 기록했다.
