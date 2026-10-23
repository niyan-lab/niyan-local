from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app import secrets_policy as sp
from app.services import config_secrets as cs
from app.settings import settings
from app.schemas.models import NiyanConfig

ROOT = Path(__file__).resolve().parents[2]


def test_policy_copies_in_sync():
    copies = [
        ROOT / "cli/niyan/secrets_policy.py",
        ROOT / "api/app/secrets_policy.py",
        ROOT / "services/gateway/secrets_policy.py",
    ]
    digests = {hashlib.sha256(p.read_bytes()).hexdigest() for p in copies}
    assert len(digests) == 1, "secrets_policy.py copies diverged; keep them identical"


@pytest.mark.parametrize("v", ["", "niyan", "sk-niyan-local", "change-me-niyan-dev-secret", "0" * 64, "__X__", "<set>", "********"])
def test_insecure_values(v):
    assert sp.is_insecure(v)


def test_strong_value_ok():
    assert not sp.is_insecure("Zq9-strong-random-value-123")


def test_allow_only_literal_one(monkeypatch):
    for v in ["true", "yes", "0", ""]:
        monkeypatch.setenv(sp.ALLOW_ENV, v)
        assert not sp.insecure_allowed()
    monkeypatch.setenv(sp.ALLOW_ENV, "1")
    assert sp.insecure_allowed()


def test_dsn_password():
    assert sp.dsn_password_insecure("postgresql://niyan:niyan@postgres:5432/niyan")
    assert not sp.dsn_password_insecure("postgresql://niyan:Strong123xyz@postgres:5432/niyan")


def test_api_refuses_defaults(monkeypatch):
    monkeypatch.delenv(sp.ALLOW_ENV, raising=False)
    monkeypatch.setattr(settings, "niyan_admin_password", "niyan")
    monkeypatch.setattr(settings, "niyan_jwt_secret", "change-me-niyan-dev-secret")
    monkeypatch.setattr(settings, "litellm_master_key", "sk-niyan-local")
    monkeypatch.setattr(settings, "pgvector_dsn", "postgresql://niyan:niyan@pg/niyan")
    bad = settings.insecure_secrets()
    assert {"NIYAN_ADMIN_PASSWORD", "NIYAN_JWT_SECRET", "LITELLM_MASTER_KEY", "PGVECTOR_DSN password"} <= set(bad)
    with pytest.raises(Exception):
        settings.assert_secure()


def _cfg():
    return NiyanConfig.model_validate(_raw())


def _raw():
    return {
        "admin_auth": {"username": "admin", "password": "realpass-abc-123456", "jwt_secret": "j" * 40},
        "proxy": {"api_keys": ["sk-real-1"]},
        "providers": {"openai": {"api_key": "sk-openai"}},
        "observability": {"public_key": "pk-lf", "secret_key": "sk-lf"},
    }


def test_strip_and_mask():
    stripped = cs.strip_secrets(_cfg())
    assert not cs.has_secrets(stripped)
    assert "realpass" not in str(stripped) and "sk-real-1" not in str(stripped) and "sk-openai" not in str(stripped)
    masked = cs.mask_secrets(_cfg())
    s = str(masked.model_dump())
    assert "realpass" not in s and "j" * 40 not in s and "sk-lf" not in s


def test_merge_keeps_current_on_defaults():
    raw = _raw()
    raw["admin_auth"]["password"] = "niyan"
    raw["admin_auth"]["jwt_secret"] = sp.MASK
    raw["proxy"]["api_keys"] = ["sk-niyan-local"]
    raw["providers"]["openai"]["api_key"] = sp.MASK
    merged = cs.merge_incoming(NiyanConfig.model_validate(raw), _cfg()).model_dump()
    assert merged["admin_auth"]["password"] == "realpass-abc-123456"
    assert merged["admin_auth"]["jwt_secret"] == "j" * 40
    assert merged["proxy"]["api_keys"] == ["sk-real-1"]
    assert merged["providers"]["openai"]["api_key"] == "sk-openai"


def test_write_private_mode(tmp_path):
    p = tmp_path / "x.yaml"
    cs.write_private(p, "a: 1\n")
    assert (p.stat().st_mode & 0o777) == 0o600


def test_loadtest_redact_job():
    from app.services.loadtest_runner import redact_job

    out = redact_job({"auth_bearer": "sk-secret", "headers": {"Authorization": "Bearer x", "X-Other": "1"}})
    assert out["auth_bearer"] == "***"
    assert out["headers"]["Authorization"] == "***" and out["headers"]["X-Other"] == "1"
