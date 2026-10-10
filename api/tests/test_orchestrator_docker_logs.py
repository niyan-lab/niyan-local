from __future__ import annotations

import sys
import types

import pytest

from app.services.orchestrator import DockerOrchestrator, ServiceNotFoundError


class _FakeContainer:
    def __init__(self, name, log_bytes):
        self.name = name
        self._log_bytes = log_bytes

    def logs(self, tail=100):
        return self._log_bytes


class _FakeContainers:
    def __init__(self, items):
        self._items = items

    def list(self, all=False):
        return self._items


class _FakeClient:
    def __init__(self, items):
        self.containers = _FakeContainers(items)


def _install_fake_docker(monkeypatch, items):
    # Patch the external `docker` SDK boundary (not internal logic).
    fake_docker = types.ModuleType("docker")
    fake_docker.from_env = lambda: _FakeClient(items)
    fake_errors = types.ModuleType("docker.errors")
    fake_errors.DockerException = Exception
    fake_docker.errors = fake_errors
    monkeypatch.setitem(sys.modules, "docker", fake_docker)
    monkeypatch.setitem(sys.modules, "docker.errors", fake_errors)


def test_stream_logs_returns_lines(monkeypatch):
    _install_fake_docker(monkeypatch, [_FakeContainer("niyan-gateway-1", b"line1\nline2\n")])
    assert DockerOrchestrator().stream_logs("gateway", tail=100) == ["line1", "line2"]


def test_stream_logs_missing_service_raises(monkeypatch):
    _install_fake_docker(monkeypatch, [_FakeContainer("niyan-other-1", b"x\n")])
    with pytest.raises(ServiceNotFoundError):
        DockerOrchestrator().stream_logs("gateway")
