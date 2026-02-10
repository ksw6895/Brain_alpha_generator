"""Authenticated Brain API session wrapper."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from ..constants import API_BASE, DEFAULT_CREDENTIALS_PATH
from ..exceptions import BrainAPIError, ManualActionRequired


@dataclass
class BrainCredentials:
    email: str
    password: str


def load_credentials(path: str | Path = DEFAULT_CREDENTIALS_PATH) -> BrainCredentials:
    """Load credentials from JSON file.

    Supported formats:
    - ["email", "password"]
    - {"email": "...", "password": "..."}
    """
    p = Path(path).expanduser()
    raw = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(raw, list) and len(raw) >= 2:
        return BrainCredentials(email=str(raw[0]), password=str(raw[1]))
    if isinstance(raw, dict) and "email" in raw and "password" in raw:
        return BrainCredentials(email=str(raw["email"]), password=str(raw["password"]))
    raise ValueError(f"Unsupported credentials schema in {p}")


def save_credentials(
    creds: BrainCredentials,
    path: str | Path = DEFAULT_CREDENTIALS_PATH,
    as_list: bool = True,
) -> Path:
    """Save credentials file with 0600 permissions."""
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload: Any
    if as_list:
        payload = [creds.email, creds.password]
    else:
        payload = {"email": creds.email, "password": creds.password}
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    p.chmod(0o600)
    return p


class BrainAPISession:
    """Thin wrapper around requests.Session with automatic re-login."""

    def __init__(
        self,
        creds: BrainCredentials,
        api_base: str = API_BASE,
        timeout_sec: int = 30,
        expiry_buffer_sec: int = 60,
    ) -> None:
        self.creds = creds
        self.api_base = api_base.rstrip("/")
        self.timeout_sec = timeout_sec
        self.expiry_buffer_sec = expiry_buffer_sec
        self.s = requests.Session()
        self.s.auth = (creds.email, creds.password)

    def _url(self, path_or_url: str) -> str:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            return path_or_url
        return f"{self.api_base}/{path_or_url.lstrip('/')}"

    def auth_post(self) -> requests.Response:
        return self.s.post(self._url("/authentication"), timeout=self.timeout_sec)

    def auth_get(self) -> requests.Response:
        return self.s.get(self._url("/authentication"), timeout=self.timeout_sec)

    def ensure_login(self, interactive: bool = False) -> None:
        """Ensure current session is authenticated and not near expiry."""
        r = self.auth_get()
        if r.status_code == 200:
            payload = r.json()
            expiry = payload.get("token", {}).get("expiry", 0)
            if isinstance(expiry, (int, float)) and expiry > self.expiry_buffer_sec:
                return
            self._login_flow(interactive=interactive)
            return
        if r.status_code in (204, 401):
            self._login_flow(interactive=interactive)
            return
        if r.status_code // 100 != 2:
            raise BrainAPIError(f"auth_get failed: {r.status_code} {r.text}")

    def _login_flow(self, interactive: bool = False) -> None:
        r = self.auth_post()
        if r.status_code == 201:
            return

        if r.status_code == 401 and r.headers.get("WWW-Authenticate") == "persona" and "Location" in r.headers:
            action_url = urljoin(r.url, r.headers["Location"])
            if not interactive:
                raise ManualActionRequired(
                    "Biometrics authentication is required to continue.",
                    action_url=action_url,
                )

            print(f"[ACTION REQUIRED] Open this URL and complete biometrics:\n{action_url}")
            input("Press Enter after completing biometrics... ")
            retry = self.s.post(action_url, timeout=self.timeout_sec)
            if retry.status_code // 100 == 2:
                return
            raise BrainAPIError(f"Biometrics follow-up failed: {retry.status_code} {retry.text}")

        if r.status_code // 100 != 2:
            raise BrainAPIError(f"Authentication failed: {r.status_code} {r.text}")

    def request(
        self,
        method: str,
        path_or_url: str,
        *,
        ensure_login: bool = True,
        interactive_login: bool = False,
        retry_unauthorized: bool = True,
        **kwargs: Any,
    ) -> requests.Response:
        """Make authenticated request with one automatic re-login retry."""
        if ensure_login:
            self.ensure_login(interactive=interactive_login)

        kwargs.setdefault("timeout", self.timeout_sec)
        url = self._url(path_or_url)
        response = self.s.request(method, url, **kwargs)

        if response.status_code == 401 and retry_unauthorized:
            self._login_flow(interactive=interactive_login)
            response = self.s.request(method, url, **kwargs)

        return response

    def get(self, path_or_url: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", path_or_url, **kwargs)

    def post(self, path_or_url: str, **kwargs: Any) -> requests.Response:
        return self.request("POST", path_or_url, **kwargs)

    def patch(self, path_or_url: str, **kwargs: Any) -> requests.Response:
        return self.request("PATCH", path_or_url, **kwargs)

    def options(self, path_or_url: str, **kwargs: Any) -> requests.Response:
        return self.request("OPTIONS", path_or_url, **kwargs)

    def poll_with_retry_after(
        self,
        path_or_url: str,
        *,
        max_wait_sec: int = 3600,
        sleep_floor_sec: float = 1.0,
    ) -> requests.Response:
        """Poll a resource respecting Retry-After headers until completion."""
        waited = 0.0
        while True:
            r = self.get(path_or_url, ensure_login=False)
            retry_after = r.headers.get("Retry-After") or r.headers.get("retry-after")
            if not retry_after:
                return r
            sleep_sec = max(float(retry_after), sleep_floor_sec)
            time.sleep(sleep_sec)
            waited += sleep_sec
            if waited > max_wait_sec:
                raise TimeoutError(f"Polling timeout: {path_or_url}")
