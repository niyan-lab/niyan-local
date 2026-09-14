"""HTTP client for niyan-api."""

from __future__ import annotations

from typing import Any, Optional

import httpx


class NiyanApiClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8100", token: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _headers(self) -> dict:
        h = {"Accept": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def healthy(self) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/api/health", timeout=2.0)
            return r.status_code == 200
        except Exception:
            return False

    def login(self, username: str, password: str) -> str:
        r = httpx.post(
            f"{self.base_url}/api/auth/login",
            json={"username": username, "password": password},
            timeout=10.0,
        )
        r.raise_for_status()
        self.token = r.json()["access_token"]
        return self.token

    def get(self, path: str) -> Any:
        r = httpx.get(f"{self.base_url}{path}", headers=self._headers(), timeout=30.0)
        r.raise_for_status()
        return r.json()

    def put(self, path: str, payload: Any) -> Any:
        r = httpx.put(
            f"{self.base_url}{path}",
            headers=self._headers(),
            json=payload,
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()

    def post(self, path: str, payload: Any = None) -> Any:
        r = httpx.post(
            f"{self.base_url}{path}",
            headers=self._headers(),
            json=payload or {},
            timeout=120.0,
        )
        r.raise_for_status()
        return r.json()

    def delete(self, path: str) -> Any:
        r = httpx.delete(f"{self.base_url}{path}", headers=self._headers(), timeout=60.0)
        r.raise_for_status()
        return r.json() if r.content else {}
