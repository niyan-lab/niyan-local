from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth import require_admin
from app.container import provide_orchestrator
from app.main import app
from app.services.orchestrator import ServiceNotFoundError


class _StubOrch:
    def stream_logs(self, service, tail=100):
        if service == "missing":
            raise ServiceNotFoundError("nope")
        if service == "broken":
            raise RuntimeError("backend down")
        return ["a", "b"]


def _client():
    app.dependency_overrides[provide_orchestrator] = lambda: _StubOrch()
    app.dependency_overrides[require_admin] = lambda: "admin"
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_logs_not_found_returns_404():
    assert _client().get("/api/logs/missing").status_code == 404


def test_logs_backend_error_returns_503():
    assert _client().get("/api/logs/broken").status_code == 503


def test_logs_ok_streams_lines():
    r = _client().get("/api/logs/gateway")
    assert r.status_code == 200
    assert "a" in r.text and "b" in r.text
