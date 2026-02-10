"""Authenticated Brain API session wrapper."""

from __future__ import annotations

import json
import os
import time
from http.cookiejar import LWPCookieJar
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from ..constants import API_BASE, DEFAULT_CREDENTIALS_PATH
from ..exceptions import BrainAPIError, ManualActionRequired

_DOTENV_LOADED = False


@dataclass
class BrainCredentials:
    email: str
    password: str


def _ensure_dotenv_loaded() -> None:
    """Best-effort .env loading for local development."""
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass
    _DOTENV_LOADED = True


def load_credentials_from_env() -> BrainCredentials | None:
    """Load credentials from environment variables if available.

    Preferred keys:
    - BRAIN_CREDENTIAL_EMAIL
    - BRAIN_CREDENTIAL_PASSWORD

    Backward-compatible keys:
    - BRAIN_EMAIL
    - BRAIN_PASSWORD
    """
    _ensure_dotenv_loaded()
    email = os.getenv("BRAIN_CREDENTIAL_EMAIL") or os.getenv("BRAIN_EMAIL")
    password = os.getenv("BRAIN_CREDENTIAL_PASSWORD") or os.getenv("BRAIN_PASSWORD")
    if email and password:
        return BrainCredentials(email=email, password=password)
    return None


def load_credentials(path: str | Path = DEFAULT_CREDENTIALS_PATH, prefer_env: bool = True) -> BrainCredentials:
    """Load credentials from env vars or JSON file.

    Supported formats:
    - ["email", "password"]
    - {"email": "...", "password": "..."}
    """
    if prefer_env:
        env_creds = load_credentials_from_env()
        if env_creds is not None:
            return env_creds

    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(
            "Credentials not found. Set BRAIN_CREDENTIAL_EMAIL/BRAIN_CREDENTIAL_PASSWORD "
            f"(for example via .env) or create {p}."
        )

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
        interactive_login_default: bool = False,
        cookie_path: str | Path | None = "~/.brain_session_cookies",
    ) -> None:
        self.creds = creds
        self.api_base = api_base.rstrip("/")
        self.timeout_sec = timeout_sec
        self.expiry_buffer_sec = expiry_buffer_sec
        self.interactive_login_default = interactive_login_default
        self.cookie_path = Path(cookie_path).expanduser() if cookie_path else None
        self.s = requests.Session()
        self.s.auth = (creds.email, creds.password)
        self._load_cookie_jar()

    def _url(self, path_or_url: str) -> str:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            return path_or_url
        return f"{self.api_base}/{path_or_url.lstrip('/')}"

    def auth_post(self) -> requests.Response:
        r = self.s.post(self._url("/authentication"), timeout=self.timeout_sec)
        if r.status_code // 100 == 2:
            self._save_cookie_jar()
        return r

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
            for _ in range(3):
                retry = self.s.post(action_url, timeout=self.timeout_sec)
                if retry.status_code // 100 == 2:
                    self._save_cookie_jar()
                    return
                if retry.status_code == 401:
                    input("Biometrics still pending. Complete it and press Enter to retry... ")
                    continue
                raise BrainAPIError(f"Biometrics follow-up failed: {retry.status_code} {retry.text}")
            raise BrainAPIError("Biometrics follow-up failed after retries.")

        if r.status_code // 100 != 2:
            raise BrainAPIError(f"Authentication failed: {r.status_code} {r.text}")

    def request(
        self,
        method: str,
        path_or_url: str,
        *,
        ensure_login: bool = True,
        interactive_login: bool | None = None,
        retry_unauthorized: bool = True,
        **kwargs: Any,
    ) -> requests.Response:
        """Make authenticated request with one automatic re-login retry."""
        if interactive_login is None:
            interactive_login = self.interactive_login_default

        if ensure_login:
            self.ensure_login(interactive=interactive_login)

        kwargs.setdefault("timeout", self.timeout_sec)
        url = self._url(path_or_url)
        response = self.s.request(method, url, **kwargs)

        if response.status_code == 401 and retry_unauthorized:
            self._login_flow(interactive=interactive_login)
            response = self.s.request(method, url, **kwargs)

        if response.status_code // 100 == 2:
            self._save_cookie_jar()
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

    def _load_cookie_jar(self) -> None:
        """Load persisted session cookies to reduce repeated login prompts."""
        if self.cookie_path is None:
            return
        self.cookie_path.parent.mkdir(parents=True, exist_ok=True)
        jar = LWPCookieJar(str(self.cookie_path))
        try:
            if self.cookie_path.exists():
                jar.load(ignore_discard=True, ignore_expires=True)
        except Exception:
            # Ignore malformed/expired cookie files and continue with fresh jar.
            pass
        self.s.cookies = jar

    def _save_cookie_jar(self) -> None:
        """Persist session cookies for reuse across CLI invocations."""
        cookies = self.s.cookies
        if not isinstance(cookies, LWPCookieJar):
            return
        try:
            cookies.save(ignore_discard=True, ignore_expires=True)
            if self.cookie_path and self.cookie_path.exists():
                self.cookie_path.chmod(0o600)
        except Exception:
            # Persistence is a best-effort optimization; do not break requests.
            pass
