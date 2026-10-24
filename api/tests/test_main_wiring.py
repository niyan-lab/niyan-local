from __future__ import annotations

from fastapi.testclient import TestClient

from app.container import get_container
from app.main import app
from app.services.config_store import ConfigReadOnlyError
from app.settings import settings
import pytest


@pytest.fixture(autouse=True)
def _secure_settings(monkeypatch):
    """Per-test strong secrets (no global insecure bypass)."""
    monkeypatch.setattr(settings, "niyan_admin_password", "T3st-admin-pass-xyz-123456")
    monkeypatch.setattr(settings, "niyan_jwt_secret", "t" * 48)
    monkeypatch.setattr(settings, "litellm_master_key", "sk-test-" + "k" * 32)
    monkeypatch.setattr(settings, "pgvector_dsn", "")
    monkeypatch.setattr(type(settings), "resolved_config_dsn", lambda self: "")


def test_container_built_on_startup():
    with TestClient(app) as client:  # triggers lifespan
        client.get("/")
        assert getattr(app.state, "container", None) is not None


def test_container_is_shared_singleton():
    with TestClient(app) as client:  # triggers lifespan
        client.get("/")
        assert app.state.container is get_container()


def test_config_readonly_maps_to_409():
    @app.get("/__test_readonly")
    def _boom():
        raise ConfigReadOnlyError("declarative")

    with TestClient(app) as client:
        r = client.get("/__test_readonly")
    assert r.status_code == 409
