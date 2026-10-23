import stat

from niyan.config import load_config
from niyan.secrets_init import ensure_secrets, is_insecure
import niyan.secrets_init as si

ENV = "POSTGRES_USER=niyan\nPOSTGRES_PASSWORD=niyan\nLANGFUSE_SALT=\nNIYAN_ADMIN_PASSWORD=niyan\n"
YAML = "proxy:\n  port: 4000\n  api_keys:\n    - sk-niyan-local\n\nadmin_auth:\n  username: admin\n  password: niyan\n  jwt_secret: change-me-niyan-dev-secret\n"


def _setup(tmp_path, env=ENV, yaml=YAML):
    (tmp_path / ".env").write_text(env)
    (tmp_path / "niyan.yaml").write_text(yaml)


def test_generates_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(si, "_pg_volume_exists", lambda: False)
    _setup(tmp_path)
    ensure_secrets(tmp_path)
    cfg = load_config(tmp_path / "niyan.yaml")
    assert not is_insecure(cfg.admin_auth.password)
    assert not is_insecure(cfg.admin_auth.jwt_secret)
    assert cfg.proxy.api_keys and not is_insecure(cfg.proxy.api_keys[0])
    env1 = (tmp_path / ".env").read_text()
    assert "NIYAN_ADMIN_PASSWORD" not in env1 and "POSTGRES_PASSWORD=niyan\n" not in env1
    assert stat.S_IMODE((tmp_path / ".env").stat().st_mode) == 0o600
    yaml1 = (tmp_path / "niyan.yaml").read_text()
    r = ensure_secrets(tmp_path)
    assert r["generated"] == []
    assert (tmp_path / ".env").read_text() == env1
    assert (tmp_path / "niyan.yaml").read_text() == yaml1


def test_keeps_data_bound_default_when_volume_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(si, "_pg_volume_exists", lambda: True)
    _setup(tmp_path)
    r = ensure_secrets(tmp_path)
    assert "POSTGRES_PASSWORD=niyan" in (tmp_path / ".env").read_text()
    assert r["warnings"]


def test_empty_placeholders(tmp_path, monkeypatch):
    monkeypatch.setattr(si, "_pg_volume_exists", lambda: False)
    _setup(tmp_path, yaml='proxy:\n  port: 4000\n  api_keys: []\n\nadmin_auth:\n  username: admin\n  password: ""\n  jwt_secret: ""\n')
    ensure_secrets(tmp_path)
    cfg = load_config(tmp_path / "niyan.yaml")
    assert cfg.proxy.port == 4000 and len(cfg.proxy.api_keys) == 1
    assert cfg.admin_auth.username == "admin" and len(cfg.admin_auth.password) > 16
