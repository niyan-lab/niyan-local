import hashlib
import stat
from pathlib import Path

import pytest

from niyan.config import load_config
from niyan.secrets_init import SecretsInitError, check_secrets, ensure_secrets, is_insecure
import niyan.secrets_init as si
from niyan.local_compose import InsecureSecretsError, assert_secure_env, placeholder_env

ENV = "POSTGRES_USER=niyan\nPOSTGRES_PASSWORD=niyan\nLANGFUSE_SALT=\nNIYAN_ADMIN_PASSWORD=niyan\n"
YAML = "proxy:\n  port: 4000\n  api_keys:\n    - sk-niyan-local\n\nadmin_auth:\n  username: admin\n  password: niyan\n  jwt_secret: change-me-niyan-dev-secret\n"
ROOT = Path(__file__).resolve().parents[2]


def _setup(tmp_path, env=ENV, yaml=YAML):
    (tmp_path / ".env").write_text(env)
    (tmp_path / "niyan.yaml").write_text(yaml)


class FakeMig:
    rows = 0
    instances = []

    def __init__(self, repo, values):
        self.rotated = None
        self.started = False
        FakeMig.instances.append(self)

    def start(self):
        self.started = True

    def rotate_password(self, pw):
        self.rotated = pw

    def count_rows(self, db, tables):
        r = FakeMig.rows
        if isinstance(r, list):
            return r.pop(0)
        return r


def _ens(tmp_path, vol, rows=0):
    si.COUNT_BACKOFF = (0, 0, 0)
    FakeMig.rows = rows
    FakeMig.instances = []
    return ensure_secrets(tmp_path, volume_probe=lambda: vol, migrator_factory=FakeMig)


def _env(tmp_path):
    return dict(l.split("=", 1) for l in (tmp_path / ".env").read_text().splitlines() if "=" in l)


def test_generates_and_is_idempotent(tmp_path):
    _setup(tmp_path)
    _ens(tmp_path, False)
    cfg = load_config(tmp_path / "niyan.yaml")
    assert not is_insecure(cfg.admin_auth.password) and len(cfg.admin_auth.password) == si.ADMIN_PASSWORD_LEN
    assert not is_insecure(cfg.admin_auth.jwt_secret)
    assert cfg.proxy.api_keys and not is_insecure(cfg.proxy.api_keys[0])
    env1 = (tmp_path / ".env").read_text()
    assert "NIYAN_ADMIN_PASSWORD" not in env1 and "POSTGRES_PASSWORD=niyan\n" not in env1
    for f in (".env", "niyan.yaml"):
        assert stat.S_IMODE((tmp_path / f).stat().st_mode) == 0o600
    yaml1 = (tmp_path / "niyan.yaml").read_text()
    r = _ens(tmp_path, None)  # docker down is fine when nothing data-bound needs work
    assert r["generated"] == [] and r["rotated"] == []
    assert (tmp_path / ".env").read_text() == env1
    assert (tmp_path / "niyan.yaml").read_text() == yaml1


def test_upgrade_rotates_pg_password_in_place(tmp_path):
    _setup(tmp_path)
    r = _ens(tmp_path, True, rows=0)
    mig = FakeMig.instances[0]
    assert mig.started and mig.rotated
    env = _env(tmp_path)
    assert env["POSTGRES_PASSWORD"] == mig.rotated and not is_insecure(env["POSTGRES_PASSWORD"])
    assert "POSTGRES_PASSWORD" in r["rotated"]
    assert "LANGFUSE_ENCRYPTION_KEY" in r["rotated"]  # no dependent rows -> safe
    assert not check_secrets({**env, "NIYAN_ADMIN_PASSWORD": "Zx" * 12, "NIYAN_JWT_SECRET": "a" * 64, "LITELLM_MASTER_KEY": "sk-" + "b" * 40})


def test_upgrade_missing_pg_key_with_volume_rotates(tmp_path):
    _setup(tmp_path, env="POSTGRES_USER=niyan\n")
    _ens(tmp_path, True)
    assert FakeMig.instances[0].rotated == _env(tmp_path)["POSTGRES_PASSWORD"]


def test_upgrade_keeps_langfuse_keys_with_data(tmp_path):
    _setup(tmp_path, env="POSTGRES_PASSWORD=niyan\nLANGFUSE_ENCRYPTION_KEY=" + "0" * 64 + "\n")
    r = _ens(tmp_path, True, rows=3)
    env = _env(tmp_path)
    assert env["LANGFUSE_ENCRYPTION_KEY"] == "0" * 64
    assert env["NIYAN_LEGACY_LANGFUSE_ENCRYPTION_KEY"] == "1"
    assert env["LANGFUSE_SALT"] == "niyan-langfuse-salt-change-me"  # missing -> old compose default
    assert not is_insecure(env["LANGFUSE_NEXTAUTH_SECRET"])
    assert any("ENCRYPTION_KEY" in w for w in r["warnings"])
    assert "LANGFUSE_ENCRYPTION_KEY" not in check_secrets(env)
    # Re-checked on the next run: still rows -> unchanged, still marked
    r2 = _ens(tmp_path, True, rows=3)
    assert r2["rotated"] == [] and _env(tmp_path) == env


def test_docker_down_fails_closed(tmp_path):
    _setup(tmp_path)
    before = ((tmp_path / ".env").read_text(), (tmp_path / "niyan.yaml").read_text())
    with pytest.raises(SecretsInitError):
        _ens(tmp_path, None)
    assert ((tmp_path / ".env").read_text(), (tmp_path / "niyan.yaml").read_text()) == before


def test_docker_down_missing_keys_fails_closed(tmp_path):
    _setup(tmp_path, env="")
    with pytest.raises(SecretsInitError):
        _ens(tmp_path, None)


def test_empty_placeholders(tmp_path):
    _setup(tmp_path, yaml='proxy:\n  port: 4000\n  api_keys: []\n\nadmin_auth:\n  username: admin\n  password: ""\n  jwt_secret: ""\n')
    _ens(tmp_path, False)
    cfg = load_config(tmp_path / "niyan.yaml")
    assert cfg.proxy.port == 4000 and len(cfg.proxy.api_keys) == 1
    assert cfg.admin_auth.username == "admin" and len(cfg.admin_auth.password) > 16


@pytest.mark.parametrize(
    "yaml,expect_keep",
    [
        # inline flow list with a real key is kept
        ('proxy:\n  port: 4000\n  api_keys: ["sk-real-abcdef1234567890", sk-niyan-local]\nadmin_auth:\n  password: niyan\n', True),
        # comments inside sections + inline comment on value
        ("# top\nproxy:\n  # keys\n  port: 4000\n  api_keys:\n    # c\n    - sk-niyan-local\nadmin_auth:\n  username: admin  # who\n  password: niyan # default\n", False),
        # 4-space indent, last section w/o trailing newline
        ("proxy:\n    port: 4000\n    api_keys:\n        - sk-niyan-local\nadmin_auth:\n    username: admin\n    password: niyan", False),
    ],
)
def test_yaml_edge_cases(tmp_path, yaml, expect_keep):
    _setup(tmp_path, yaml=yaml)
    _ens(tmp_path, False)
    cfg = load_config(tmp_path / "niyan.yaml")
    assert cfg.proxy.port == 4000
    assert not is_insecure(cfg.admin_auth.password)
    assert cfg.admin_auth.username == "admin"
    assert all(not is_insecure(k) for k in cfg.proxy.api_keys) and cfg.proxy.api_keys
    if expect_keep:
        assert cfg.proxy.api_keys == ["sk-real-abcdef1234567890"]
    assert "sk-niyan-local" not in (tmp_path / "niyan.yaml").read_text()


def test_yaml_crlf_preserved(tmp_path):
    _setup(tmp_path, yaml=YAML.replace("\n", "\r\n"))
    _ens(tmp_path, False)
    raw = (tmp_path / "niyan.yaml").read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
    cfg = load_config(tmp_path / "niyan.yaml")
    assert not is_insecure(cfg.admin_auth.password)


def test_refuse_defaults_covers_all():
    env = {
        "NIYAN_ADMIN_PASSWORD": "niyan", "NIYAN_JWT_SECRET": "change-me-niyan-dev-secret",
        "LITELLM_MASTER_KEY": "sk-niyan-local", "POSTGRES_PASSWORD": "niyan",
        "LANGFUSE_NEXTAUTH_SECRET": "niyan-langfuse-nextauth-secret-change-me",
        "LANGFUSE_SALT": "niyan-langfuse-salt-change-me", "LANGFUSE_ENCRYPTION_KEY": "0" * 64,
    }
    assert set(check_secrets(env)) == set(env)
    with pytest.raises(InsecureSecretsError):
        assert_secure_env(env)
    for v in ("true", "yes", "TRUE"):
        with pytest.raises(InsecureSecretsError):
            assert_secure_env({**env, "NIYAN_ALLOW_INSECURE_DEFAULTS": v})
    assert_secure_env({**env, "NIYAN_ALLOW_INSECURE_DEFAULTS": "1"})


def test_placeholder_env_never_secure():
    env = placeholder_env({})
    assert env["POSTGRES_PASSWORD"] and check_secrets(env)


def test_policy_copies_in_sync():
    copies = [ROOT / "cli/niyan/secrets_policy.py", ROOT / "api/app/secrets_policy.py", ROOT / "services/gateway/secrets_policy.py"]
    assert len({hashlib.sha256(p.read_bytes()).hexdigest() for p in copies}) == 1


# ---- migrator hardening (07 follow-up)

import subprocess


class ExecMig(si.PgMigrator):
    """Real PgMigrator logic with a scripted exec()."""

    def __init__(self, results):
        self.user = "niyan"
        self.results = list(results)
        self.calls = []

    def exec(self, args, stdin=None, check=True):
        self.calls.append(stdin)
        r = self.results.pop(0)
        return r() if callable(r) else r


def _cp(rc, out="", err=""):
    return subprocess.CompletedProcess([], rc, out, err)


def test_role_does_not_exist_is_unknown_not_zero():
    # DB exists, but the count fails with a role error: must NOT be treated as 0.
    m = ExecMig([_cp(0, "1\n"), _cp(2, "", 'psql: error: FATAL:  role "niyan" does not exist')])
    assert m.count_rows("langfuse", ["api_keys"]) is None
    # and when the existence probe itself fails with a role error -> unknown
    m = ExecMig([_cp(2, "", 'FATAL:  role "niyan" does not exist')])
    assert m.count_rows("langfuse", ["api_keys"]) is None


def test_missing_database_is_zero():
    assert ExecMig([_cp(0, "0\n")]).count_rows("langfuse", ["api_keys"]) == 0
    assert si.missing_database('FATAL:  3D000: database "langfuse" does not exist', "langfuse")
    assert si.missing_database('psql: error: FATAL:  database "langfuse" does not exist', "langfuse")
    assert not si.missing_database('FATAL:  role "langfuse" does not exist', "langfuse")
    assert not si.missing_database('ERROR:  relation "database" does not exist', "langfuse")


def test_exec_timeout_is_unknown(monkeypatch):
    def boom(*a, **k):
        raise subprocess.TimeoutExpired(a[0], 120)

    monkeypatch.setattr(si, "_run", boom)
    m = si.PgMigrator.__new__(si.PgMigrator)
    m.user, m.base, m.repo, m.env = "niyan", ["docker"], Path("."), {}
    r = m.exec(["true"], check=False)
    assert r.returncode == 124
    assert m.count_rows("langfuse", ["api_keys"]) is None


def test_rowcount_failure_no_pin_no_marker_nothing_rotated(tmp_path):
    env0 = "POSTGRES_PASSWORD=niyan\nLANGFUSE_SALT=niyan-langfuse-salt-change-me\n"
    _setup(tmp_path, env=env0)
    before = ((tmp_path / ".env").read_bytes(), (tmp_path / "niyan.yaml").read_bytes())
    with pytest.raises(SecretsInitError, match="re-run"):
        _ens(tmp_path, True, rows=None)
    assert ((tmp_path / ".env").read_bytes(), (tmp_path / "niyan.yaml").read_bytes()) == before
    assert FakeMig.instances[0].rotated is None  # pg password not touched either
    env = _env(tmp_path)
    assert "NIYAN_LEGACY_LANGFUSE_SALT" not in env
    assert "LANGFUSE_SALT" in check_secrets(env)  # startup keeps refusing
    # transient: succeeds on retry
    r = _ens(tmp_path, True, rows=[None, None, 0, 0])
    assert "LANGFUSE_SALT" in r["rotated"] and "POSTGRES_PASSWORD" in r["rotated"]


def test_marked_key_rechecked_and_rotated_when_safe(tmp_path):
    _setup(tmp_path, env="POSTGRES_PASSWORD=" + "a" * 48 + "\nLANGFUSE_SALT=niyan-langfuse-salt-change-me\nNIYAN_LEGACY_LANGFUSE_SALT=1\n")
    r = _ens(tmp_path, True, rows=0)
    env = _env(tmp_path)
    assert "LANGFUSE_SALT" in r["rotated"] and not is_insecure(env["LANGFUSE_SALT"])
    assert "NIYAN_LEGACY_LANGFUSE_SALT" not in env


def test_marked_key_unknown_count_keeps_marker(tmp_path):
    _setup(tmp_path, env="POSTGRES_PASSWORD=" + "a" * 48 + "\nLANGFUSE_SALT=niyan-langfuse-salt-change-me\nNIYAN_LEGACY_LANGFUSE_SALT=1\n")
    with pytest.raises(SecretsInitError):
        _ens(tmp_path, True, rows=None)
    assert _env(tmp_path)["NIYAN_LEGACY_LANGFUSE_SALT"] == "1"


def test_marked_key_docker_down_is_kept(tmp_path):
    _setup(tmp_path, env="POSTGRES_PASSWORD=" + "a" * 48 + "\nLANGFUSE_SALT=niyan-langfuse-salt-change-me\nNIYAN_LEGACY_LANGFUSE_SALT=1\nLANGFUSE_ENCRYPTION_KEY=" + "b" * 64 + "\n")
    r = _ens(tmp_path, None)
    assert _env(tmp_path)["LANGFUSE_SALT"] == "niyan-langfuse-salt-change-me"
    assert any("not re-checked" in w for w in r["warnings"])
