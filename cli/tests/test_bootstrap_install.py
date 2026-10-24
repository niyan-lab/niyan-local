"""Runs bootstrap/install.sh end-to-end against a temp NIYAN_HOME with a fake `docker`."""
import hashlib
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(not BASH or not shutil.which("openssl"), reason="bash/openssl required")

FAKE_DOCKER = r'''#!/usr/bin/env bash
args="$*"
case "$1" in
  info) [ "${FAKE_DOCKER_DOWN:-0}" = 1 ] && exit 1; exit 0 ;;
  volume) [ "${FAKE_VOL:-0}" = 1 ] && exit 0; exit 1 ;;
  compose)
    case "$args" in
      *"exec -T postgres psql"*)
        sql="$(cat)"
        printf '%s\n' "$sql" >>"$FAKE_LOG"
        case "$sql" in
          "select 1;") echo 1 ;;
          *pg_database*) if [ -n "${FAKE_DB_FAIL:-}" ]; then echo "$FAKE_DB_FAIL" >&2; exit 2; fi; echo "${FAKE_DB_EXISTS:-1}" ;;
          *ALTER*) echo ALTER ;;
          *) if [ -n "${FAKE_COUNT_FAIL:-}" ]; then echo "$FAKE_COUNT_FAIL" >&2; exit 2; fi; echo "${FAKE_COUNT:-0}" ;;
        esac ;;
      *"exec -T postgres sh"*) cat >/dev/null; echo 1 ;;
      *) exit 0 ;;
    esac ;;
esac
exit 0
'''


def _run(tmp_path, **fake):
    fb = tmp_path / "fakebin"
    fb.mkdir(exist_ok=True)
    d = fb / "docker"
    d.write_text(FAKE_DOCKER)
    d.chmod(0o755)
    env = {
        "PATH": f"{fb}:/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(tmp_path), "SHELL": "/bin/bash",
        "NIYAN_HOME": str(tmp_path / ".niyan"), "NIYAN_LOCAL_BIN": str(tmp_path / "lbin"),
        "NIYAN_PULL_ON_INSTALL": "0", "NIYAN_COUNT_BACKOFF": "0", "NIYAN_READY_SLEEP": "0",
        "FAKE_LOG": str(tmp_path / "psql.log"), **fake,
    }
    return subprocess.run([BASH, str(ROOT / "bootstrap/install.sh")], capture_output=True, text=True, env=env)


def _stack(tmp_path):
    return tmp_path / ".niyan" / "stack"


def _env(tmp_path):
    return dict(l.split("=", 1) for l in (_stack(tmp_path) / ".env").read_text().splitlines() if "=" in l and not l.startswith("#"))


def _yaml(tmp_path):
    import yaml
    return yaml.safe_load((_stack(tmp_path) / "niyan.yaml").read_text())


def _hash(tmp_path):
    return [hashlib.sha256((_stack(tmp_path) / f).read_bytes()).hexdigest() for f in (".env", "niyan.yaml")]


def _preseed(tmp_path, env_text):
    s = _stack(tmp_path)
    s.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "bootstrap/stack/niyan.example.yaml", s / "niyan.yaml")
    (s / ".env").write_text(env_text)


def test_fresh_writes_yaml_single_source(tmp_path):
    r = _run(tmp_path)
    assert r.returncode == 0, r.stderr
    env, y = _env(tmp_path), _yaml(tmp_path)
    assert y["proxy"]["api_keys"][0] == env["LITELLM_MASTER_KEY"]
    assert y["admin_auth"]["password"] == env["NIYAN_ADMIN_PASSWORD"] and len(env["NIYAN_ADMIN_PASSWORD"]) == 24
    assert y["admin_auth"]["jwt_secret"] == env["NIYAN_JWT_SECRET"]
    for f in (".env", "niyan.yaml"):
        assert stat.S_IMODE((_stack(tmp_path) / f).stat().st_mode) == 0o600
    h = _hash(tmp_path)
    assert _run(tmp_path).returncode == 0 and _hash(tmp_path) == h  # idempotent


def test_yaml_wins_over_env(tmp_path):
    assert _run(tmp_path).returncode == 0
    p = _stack(tmp_path) / "niyan.yaml"
    p.write_text(p.read_text().replace(_env(tmp_path)["LITELLM_MASTER_KEY"], "sk-niyan-" + "9" * 48))
    assert _run(tmp_path).returncode == 0
    assert _env(tmp_path)["LITELLM_MASTER_KEY"] == "sk-niyan-" + "9" * 48


def test_rowcount_failure_no_pin_no_marker(tmp_path):
    _preseed(tmp_path, "POSTGRES_PASSWORD=niyan\nLANGFUSE_SALT=niyan-langfuse-salt-change-me\n")
    (tmp_path / "psql.log").write_text("")
    r = _run(tmp_path, FAKE_VOL="1", FAKE_COUNT_FAIL="ERROR: canceling statement")
    assert r.returncode != 0 and "re-run" in r.stderr
    env = _env(tmp_path)  # no pin, no marker, nothing rotated
    assert env["POSTGRES_PASSWORD"] == "niyan" and env["LANGFUSE_SALT"] == "niyan-langfuse-salt-change-me"
    assert not any(k.startswith("NIYAN_LEGACY") for k in env)
    assert "ALTER" not in (tmp_path / "psql.log").read_text()  # pg password untouched
    assert (tmp_path / "psql.log").read_text().count("query_to_xml") == 3  # retried
    r = _run(tmp_path, FAKE_VOL="1", FAKE_COUNT="0")
    assert r.returncode == 0, r.stderr
    env = _env(tmp_path)
    assert env["POSTGRES_PASSWORD"] != "niyan" and "change-me" not in env["LANGFUSE_SALT"]
    assert "NIYAN_LEGACY_LANGFUSE_SALT" not in env


def test_role_error_is_unknown(tmp_path):
    _preseed(tmp_path, "POSTGRES_PASSWORD=" + "c" * 48 + "\nLANGFUSE_SALT=niyan-langfuse-salt-change-me\n")
    r = _run(tmp_path, FAKE_VOL="1", FAKE_DB_FAIL='psql: error: FATAL:  role "niyan" does not exist')
    assert r.returncode != 0
    assert _env(tmp_path)["LANGFUSE_SALT"] == "niyan-langfuse-salt-change-me"
    assert "NIYAN_LEGACY_LANGFUSE_SALT" not in _env(tmp_path)


def test_missing_langfuse_db_counts_zero(tmp_path):
    _preseed(tmp_path, "POSTGRES_PASSWORD=" + "c" * 48 + "\nLANGFUSE_SALT=niyan-langfuse-salt-change-me\n")
    r = _run(tmp_path, FAKE_VOL="1", FAKE_DB_EXISTS="0")
    assert r.returncode == 0, r.stderr
    env = _env(tmp_path)
    assert "change-me" not in env["LANGFUSE_SALT"] and "NIYAN_LEGACY_LANGFUSE_SALT" not in env


def test_marker_only_on_confirmed_rows_and_rechecked(tmp_path):
    _preseed(tmp_path, "POSTGRES_PASSWORD=" + "c" * 48 + "\nLANGFUSE_SALT=niyan-langfuse-salt-change-me\n")
    assert _run(tmp_path, FAKE_VOL="1", FAKE_COUNT="3").returncode == 0
    env = _env(tmp_path)
    assert env["LANGFUSE_SALT"] == "niyan-langfuse-salt-change-me" and env["NIYAN_LEGACY_LANGFUSE_SALT"] == "1"
    # Docker down + only marked keys pending: kept, install still succeeds
    assert _run(tmp_path, FAKE_DOCKER_DOWN="1").returncode == 0
    assert _env(tmp_path)["NIYAN_LEGACY_LANGFUSE_SALT"] == "1"
    # rows gone -> rotated, marker dropped
    assert _run(tmp_path, FAKE_VOL="1", FAKE_COUNT="0").returncode == 0
    env = _env(tmp_path)
    assert "change-me" not in env["LANGFUSE_SALT"] and "NIYAN_LEGACY_LANGFUSE_SALT" not in env


def test_bin_niyan_rotate_gateway_key(tmp_path):
    assert _run(tmp_path).returncode == 0
    old = _env(tmp_path)["LITELLM_MASTER_KEY"]
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "NIYAN_HOME": str(tmp_path / ".niyan")}
    r = subprocess.run([BASH, str(tmp_path / ".niyan/bin/niyan"), "secrets", "rotate", "gateway-key"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    new = _env(tmp_path)["LITELLM_MASTER_KEY"]
    assert new != old and new not in r.stdout
    assert _yaml(tmp_path)["proxy"]["api_keys"] == [new]
