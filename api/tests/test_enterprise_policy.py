"""Unit tests for gateway enterprise policy resolver."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_policy():
    path = Path(__file__).resolve().parents[2] / "services" / "gateway" / "policy.py"
    spec = importlib.util.spec_from_file_location("niyan_gateway_policy", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


policy = _load_policy()

SAMPLE = {
    "enabled": True,
    "mode": "manual",
    "domains": [
        {
            "id": "finance",
            "enabled": True,
            "deployment": "local",
            "local_model": "llama3.2:3b",
            "proprietary_model": "gemini-2.5-flash",
        },
        {
            "id": "research",
            "enabled": True,
            "deployment": "proprietary",
            "local_model": "llama3.2:3b",
            "proprietary_model": "gemini-2.5-flash",
        },
        {
            "id": "legal",
            "enabled": False,
            "deployment": "local",
            "local_model": "llama3.2:3b",
            "proprietary_model": "gemini-2.5-flash",
        },
    ],
}


def test_passthrough_real_model():
    r = policy.resolve_model("llama3.2:3b", SAMPLE)
    assert r.ok and not r.via_policy
    assert r.resolved_model == "llama3.2:3b"


def test_domain_local():
    r = policy.resolve_model("finance", SAMPLE)
    assert r.ok and r.via_policy
    assert r.domain == "finance"
    assert r.deployment == "local"
    assert r.resolved_model == "llama3.2:3b"


def test_domain_case_insensitive_proprietary():
    r = policy.resolve_model("Research", SAMPLE)
    assert r.ok and r.via_policy
    assert r.resolved_model == "gemini-2.5-flash"
    assert r.deployment == "proprietary"


def test_disabled_domain_errors():
    r = policy.resolve_model("legal", SAMPLE)
    assert not r.ok
    assert "disabled" in (r.error or "")


def test_policy_disabled_passthrough():
    r = policy.resolve_model("finance", {**SAMPLE, "enabled": False})
    assert r.ok and not r.via_policy
    assert r.resolved_model == "finance"


def test_empty_model_errors():
    r = policy.resolve_model("  ", SAMPLE)
    assert not r.ok
