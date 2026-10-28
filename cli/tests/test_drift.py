"""Admin password drift between niyan.yaml and .env (never printed)."""
from types import SimpleNamespace

from typer.testing import CliRunner

from niyan import main as m
from niyan.drift import admin_password_drift

YAML_PW = "yaml-Secret-" + "a" * 20
ENV_PW = "env-Secret-" + "b" * 20


def test_no_env_or_no_key_is_not_drift(tmp_path):
    assert not admin_password_drift(tmp_path, YAML_PW)
    (tmp_path / ".env").write_text("POSTGRES_PASSWORD=x\n")
    assert not admin_password_drift(tmp_path, YAML_PW)


def test_matching_value_is_not_drift(tmp_path):
    (tmp_path / ".env").write_text(f'NIYAN_ADMIN_PASSWORD="{YAML_PW}"\n')
    assert not admin_password_drift(tmp_path, YAML_PW)


def test_different_value_is_drift(tmp_path):
    (tmp_path / ".env").write_text(f"# c\nNIYAN_ADMIN_PASSWORD={ENV_PW}\n")
    assert admin_password_drift(tmp_path, YAML_PW)


def _cfg():
    return SimpleNamespace(admin_auth=SimpleNamespace(username="admin", password=YAML_PW))


class _Down:
    def healthy(self):
        return False


def test_status_warns_without_printing_secrets(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(f"NIYAN_ADMIN_PASSWORD={ENV_PW}\n")
    monkeypatch.setattr(m, "_repo", lambda: tmp_path)
    monkeypatch.setattr(m, "_load", lambda repo: _cfg())
    monkeypatch.setattr(m, "_api", lambda repo, login=False: _Down())
    monkeypatch.setattr(m, "detect_profile", lambda *a: (_ for _ in ()).throw(SystemExit(0)))
    out = CliRunner().invoke(m.app, ["status"]).output
    assert "differs from niyan.yaml" in out
    assert ENV_PW not in out and YAML_PW not in out


def test_up_warns_before_starting(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(f"NIYAN_ADMIN_PASSWORD={ENV_PW}\n")
    monkeypatch.setattr(m, "_repo", lambda: tmp_path)
    cfg = _cfg()
    monkeypatch.setattr(m, "_load", lambda repo: cfg)

    def stop(*a, **k):
        raise SystemExit(0)

    monkeypatch.setattr(m, "detect_profile", stop)
    out = CliRunner().invoke(m.app, ["up"]).output
    assert "differs from niyan.yaml" in out
    assert ENV_PW not in out and YAML_PW not in out
