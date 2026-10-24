"""uninstall.sh and bootstrap `niyan uninstall` must not delete anything when Compose fails."""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASH = "/bin/bash" if Path("/bin/bash").exists() else shutil.which("bash")


def _fake_docker(bin_dir: Path, rc: int) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    d = bin_dir / "docker"
    d.write_text(f"#!/bin/sh\nexit {rc}\n")
    d.chmod(d.stat().st_mode | stat.S_IEXEC)


def _checkout(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "deploy").mkdir(parents=True)
    shutil.copy(ROOT / "uninstall.sh", repo / "uninstall.sh")
    shutil.copy(ROOT / "deploy" / "docker-compose.yml", repo / "deploy" / "docker-compose.yml")
    (repo / "niyan.yaml").write_text("profile: auto\n")
    (repo / ".env").write_text("X=1\n")
    (repo / ".venv").mkdir()
    return repo


def _env(tmp_path: Path, rc: int) -> dict:
    bin_dir = tmp_path / "bin"
    _fake_docker(bin_dir, rc)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "HOME": str(home),
            "NIYAN_UNINSTALL_SKIP_CLI": "1"}


def test_uninstall_sh_compose_failure_keeps_everything(tmp_path):
    repo = _checkout(tmp_path)
    r = subprocess.run([BASH, str(repo / "uninstall.sh"), "--yes"], env=_env(tmp_path, 1),
                       capture_output=True, text=True)
    assert r.returncode == 3, r.stderr
    assert "Nothing was removed" in r.stderr
    for name in ("niyan.yaml", ".env", ".venv"):
        assert (repo / name).exists(), name


def test_uninstall_sh_compose_success_removes(tmp_path):
    repo = _checkout(tmp_path)
    r = subprocess.run([BASH, str(repo / "uninstall.sh"), "--yes"], env=_env(tmp_path, 0),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    for name in ("niyan.yaml", ".env", ".venv"):
        assert not (repo / name).exists(), name


def _bootstrap(tmp_path: Path, rc: int, *args: str, stdin: str | None = None):
    niyan_home = tmp_path / "niyanhome"
    (niyan_home / "stack").mkdir(parents=True, exist_ok=True)
    (niyan_home / "stack" / "docker-compose.yml").write_text("services: {}\n")
    env = {**_env(tmp_path, rc), "NIYAN_HOME": str(niyan_home)}
    r = subprocess.run([BASH, str(ROOT / "bootstrap" / "bin" / "niyan"), "uninstall", *args],
                       env=env, capture_output=True, text=True, input=stdin)
    return r, niyan_home


def test_bootstrap_rejects_unknown_flag(tmp_path):
    r, home = _bootstrap(tmp_path, 0, "--voulmes", "--yes")
    assert r.returncode == 2
    assert "unknown flag" in r.stderr
    assert home.exists()


def test_bootstrap_refuses_without_tty_or_yes(tmp_path):
    r, home = _bootstrap(tmp_path, 0, stdin="")
    assert r.returncode == 2
    assert "--yes" in r.stderr
    assert home.exists()


def test_bootstrap_compose_failure_keeps_home(tmp_path):
    r, home = _bootstrap(tmp_path, 1, "--yes")
    assert r.returncode == 3
    assert home.exists()


def test_bootstrap_yes_removes_home(tmp_path):
    r, home = _bootstrap(tmp_path, 0, "--yes")
    assert r.returncode == 0, r.stderr
    assert not home.exists()


def test_uninstall_sh_falls_back_when_cli_exits_4(tmp_path):
    """CLI without niyan.yaml exits 4; uninstall.sh must still stop the stack via its fallback."""
    repo = _checkout(tmp_path)
    (repo / "niyan.yaml").unlink()
    cli = repo / ".venv" / "bin" / "niyan"
    cli.parent.mkdir(parents=True)
    cli.write_text("#!/bin/sh\nexit 4\n")
    cli.chmod(0o755)
    log = tmp_path / "docker.log"
    env = {**_env(tmp_path, 0)}
    bin_dir = tmp_path / "bin"
    (bin_dir / "docker").write_text(f'#!/bin/sh\necho "$@" >> "{log}"\nexit 0\n')
    env.pop("NIYAN_UNINSTALL_SKIP_CLI")
    env["PATH"] = f"{bin_dir}:{os.environ['PATH']}"
    r = subprocess.run([BASH, str(repo / "uninstall.sh"), "--yes"], env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "down" in log.read_text()
    assert not (repo / ".venv").exists()
