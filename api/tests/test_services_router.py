from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth import require_admin
from app.container import provide_orchestrator
from app.main import app
from app.schemas.models import ServiceStatus


class _StubOrch:
    def list_services(self):
        return [ServiceStatus(name="gateway", status="running", healthy=True)]

    def restart_service(self, name):
        return ServiceStatus(name=name, status="restarted", healthy=True)


def _client():
    app.dependency_overrides[provide_orchestrator] = lambda: _StubOrch()
    app.dependency_overrides[require_admin] = lambda: "admin"
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_services_uses_injected_orchestrator():
    r = _client().get("/api/services")
    assert r.status_code == 200
    assert r.json()["services"][0]["name"] == "gateway"


def test_restart_uses_injected_orchestrator():
    r = _client().post("/api/services/gateway/restart")
    assert r.status_code == 200
    assert r.json()["status"] == "restarted"
