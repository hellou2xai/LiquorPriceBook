"""Shared fixtures for integration tests against the live Render API."""

import os
from pathlib import Path

import pytest
import urllib.request
import json

# Load .env from project root (no extra dependency needed)
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


def _get_env(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        pytest.skip(f"{key} not set — skipping live API tests")
    return val


@pytest.fixture(scope="session")
def api_url() -> str:
    return _get_env("LPB_API_URL").rstrip("/")


@pytest.fixture(scope="session")
def token() -> str:
    return _get_env("LPB_ADMIN_TOKEN")


@pytest.fixture(scope="session")
def auth_headers(token) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


class APIError(Exception):
    def __init__(self, status_code: int, detail: str, url: str):
        self.status_code = status_code
        self.detail = detail
        self.url = url
        super().__init__(f"HTTP {status_code} on {url}: {detail}")


class LiveAPI:
    """Thin wrapper around urllib for live API calls (no requests dependency)."""

    def __init__(self, base_url: str, headers: dict):
        self.base_url = base_url
        self.headers = headers

    def _call(self, method: str, path: str, body: dict | None = None):
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=self.headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read()
                if not raw:
                    return {"_status": resp.status}
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise APIError(e.code, detail, url) from None

    def get(self, path: str):
        return self._call("GET", path)

    def post(self, path: str, body: dict | None = None):
        return self._call("POST", path, body or {})

    def patch(self, path: str, body: dict):
        return self._call("PATCH", path, body)

    def delete(self, path: str):
        return self._call("DELETE", path)


@pytest.fixture(scope="session")
def api(api_url, auth_headers) -> LiveAPI:
    return LiveAPI(api_url, auth_headers)
