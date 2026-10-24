from __future__ import annotations

from app.container import build_container
from app.services.config_store import DbConfigStore, FileConfigStore
from app.services.orchestrator import DockerOrchestrator


def test_vm_container_wires_docker_and_file_store(monkeypatch):
    monkeypatch.setattr("app.container.settings.niyan_config_dsn", "")
    monkeypatch.setattr("app.container.settings.niyan_config_pghost", "")
    c = build_container(platform="vm")
    assert c.platform == "vm"
    assert isinstance(c.orchestrator, DockerOrchestrator)
    assert isinstance(c.config_store, FileConfigStore)
    assert c.config_store.writable is True


def test_kubernetes_platform_coerced_to_vm_docker(monkeypatch):
    """niyan-local never wires a K8s orchestrator."""
    monkeypatch.setattr("app.container.settings.niyan_config_dsn", "")
    monkeypatch.setattr("app.container.settings.niyan_config_pghost", "")
    c = build_container(platform="kubernetes")
    assert c.platform == "vm"
    assert isinstance(c.orchestrator, DockerOrchestrator)


def test_dsn_selects_db_store(monkeypatch):
    monkeypatch.setattr(
        "app.container.settings.niyan_config_dsn",
        "postgresql://fake-user:fake-test-password@fake-host:5432/fake-db",
    )
    c = build_container(platform="vm")
    assert isinstance(c.config_store, DbConfigStore)
    assert c.config_store.writable is True


def test_explicit_overrides_win():
    sentinel = object()
    c = build_container(platform="vm", orchestrator=sentinel)
    assert c.orchestrator is sentinel
