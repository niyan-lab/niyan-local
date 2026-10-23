"""Niyan Locust scenarios — gateway presets + custom HTTP endpoint.

Job spec is loaded from LOADTEST_JOB_PATH (JSON written by niyan-api).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

from locust import HttpUser, between, task
from locust.exception import StopUser

import listener  # noqa: F401 — registers live.json hooks


def _load_job() -> Dict[str, Any]:
    path = Path(os.environ.get("LOADTEST_JOB_PATH", "/data/loadtests/current/job.json"))
    return json.loads(path.read_text())


JOB = _load_job()


def _auth_headers(job: Dict[str, Any]) -> Dict[str, str]:
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    token = (job.get("auth_bearer") or "").strip()
    if not token and job.get("use_gateway_key"):
        token = os.environ.get("NIYAN_LOADTEST_BEARER", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    custom = job.get("headers") or {}
    if isinstance(custom, dict):
        for k, v in custom.items():
            headers[str(k)] = str(v)
    return headers


def _resolve_host(job: Dict[str, Any]) -> str:
    if str(job.get("target_type") or "") == "custom":
        url = str(job.get("url") or "")
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    return str(job.get("host") or "http://gateway:4000")


def _parse_tokens(response) -> None:  # type: ignore[no-untyped-def]
    try:
        data = response.json()
        usage = data.get("usage") or {}
        total = usage.get("total_tokens")
        if total is None and isinstance(data.get("niyan"), dict):
            total = (data["niyan"].get("usage") or {}).get("total_tokens")
        if total:
            listener.add_tokens(int(total))
    except Exception:
        pass


class NiyanLoadUser(HttpUser):
    wait_time = between(0.1, 0.5)
    host = _resolve_host(JOB)

    def on_start(self) -> None:
        self.job = JOB
        self.target = str(self.job.get("target_type") or "gateway_chat")
        self.headers = _auth_headers(self.job)

    @task
    def hit(self) -> None:
        if self.target in {"gateway_chat", "gateway_domain"}:
            self._chat()
        elif self.target == "gateway_embeddings":
            self._embeddings()
        elif self.target == "custom":
            self._custom()
        else:
            raise StopUser()

    def _chat(self) -> None:
        model = self.job.get("model") or "llama3.2:3b"
        messages = self.job.get("messages") or [
            {"role": "user", "content": "Say hi in five words."}
        ]
        with self.client.post(
            "/v1/chat/completions",
            json={"model": model, "messages": messages},
            headers=self.headers,
            name="gateway_chat",
            catch_response=True,
        ) as resp:
            if resp.status_code >= 400:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")
            else:
                _parse_tokens(resp)
                resp.success()

    def _embeddings(self) -> None:
        model = self.job.get("model") or "nomic-embed-text"
        inp = self.job.get("input") or "Niyan load test embedding input"
        with self.client.post(
            "/v1/embeddings",
            json={"model": model, "input": inp},
            headers=self.headers,
            name="gateway_embeddings",
            catch_response=True,
        ) as resp:
            if resp.status_code >= 400:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")
            else:
                _parse_tokens(resp)
                resp.success()

    def _custom(self) -> None:
        method = str(self.job.get("method") or "POST").upper()
        url = str(self.job.get("url") or "")
        if not url:
            raise StopUser()
        parsed = urlparse(url)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        body = self.job.get("body")
        json_body = None
        data = None
        if body is not None:
            if isinstance(body, (dict, list)):
                json_body = body
            elif isinstance(body, str) and body.strip():
                try:
                    json_body = json.loads(body)
                except json.JSONDecodeError:
                    data = body

        with self.client.request(
            method,
            path,
            headers=self.headers,
            json=json_body,
            data=data,
            name="custom",
            catch_response=True,
        ) as resp:
            if resp.status_code >= 400:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")
            else:
                resp.success()
