from __future__ import annotations

import importlib

from app import platform as platform_mod


def _resolve(monkeypatch, **env):
    for k in ("NIYAN_PLATFORM", "NIYAN_ORCHESTRATOR"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(platform_mod)
    return platform_mod.resolve_platform()


def test_default_is_vm(monkeypatch):
    assert _resolve(monkeypatch) == "vm"


def test_kubernetes_env_ignored(monkeypatch):
    assert _resolve(monkeypatch, NIYAN_PLATFORM="kubernetes") == "vm"


def test_legacy_orchestrator_env_ignored(monkeypatch):
    assert _resolve(monkeypatch, NIYAN_ORCHESTRATOR="k8s") == "vm"
