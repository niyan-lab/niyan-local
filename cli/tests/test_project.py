"""Compose project name, repo-root source, and stale-image warnings."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from niyan import project as P
from niyan.local_compose import build_env, built_services, compose_cmd
from niyan.config import NiyanConfig, Profile


def _repo(tmp_path: Path, env_text=None) -> Path:
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "docker-compose.yml").write_text("services: {}\n")
    if env_text is not None:
        (tmp_path / ".env").write_text(env_text)
    return tmp_path


def test_new_install_uses_repo_default(tmp_path):
    assert P.compose_project(_repo(tmp_path), {}) == (P.DEFAULT_PROJECT, "default")


def test_existing_env_without_key_keeps_legacy_niyan(tmp_path):
    name, src = P.compose_project(_repo(tmp_path, "POSTGRES_USER=niyan\n"), {})
    assert name == "niyan" and "pre-existing" in src
    assert P.pg_volume(name) == "niyan_niyan_pg"


def test_env_file_key_wins_over_legacy(tmp_path):
    repo = _repo(tmp_path, "NIYAN_COMPOSE_PROJECT=\"my-stack\"\n")
    assert P.compose_project(repo, {})[0] == "my-stack"


def test_environment_wins_over_env_file(tmp_path):
    repo = _repo(tmp_path, "NIYAN_COMPOSE_PROJECT=from-file\n")
    name, src = P.compose_project(repo, {"NIYAN_COMPOSE_PROJECT": "from-env"})
    assert name == "from-env" and "environment" in src


def test_invalid_name_rejected(tmp_path):
    with pytest.raises(ValueError):
        P.compose_project(_repo(tmp_path), {"NIYAN_COMPOSE_PROJECT": "Bad Name"})


def test_example_env_pins_repo_default():
    root = Path(__file__).resolve().parents[2]
    text = (root / ".env.example").read_text()
    assert f"NIYAN_COMPOSE_PROJECT={P.DEFAULT_PROJECT}\n" in text


def test_compose_cmd_and_env_use_project(tmp_path, monkeypatch):
    monkeypatch.delenv("NIYAN_COMPOSE_PROJECT", raising=False)
    monkeypatch.delenv("COMPOSE_PROJECT_NAME", raising=False)
    repo = _repo(tmp_path, "NIYAN_COMPOSE_PROJECT=proj-x\n")
    cfg = NiyanConfig()
    cmd = compose_cmd(repo, Profile.mac, cfg)
    assert cmd[cmd.index("--project-name") + 1] == "proj-x"
    assert build_env(repo, Profile.mac, cfg)["COMPOSE_PROJECT_NAME"] == "proj-x"


def test_repo_root_source(tmp_path):
    repo = _repo(tmp_path)
    assert P.repo_root_source(repo, {"NIYAN_ROOT": str(repo)}) == f"NIYAN_ROOT={repo}"
    assert P.repo_root_source(repo, {"NIYAN_HOME": str(repo)}).startswith("NIYAN_HOME=")
    sub = repo / "deploy"
    assert P.repo_root_source(repo, {}, cwd=sub) == "current directory"
    other = tmp_path.parent
    assert "install location" in P.repo_root_source(repo, {"NIYAN_ROOT": "/nonexistent"}, cwd=other)


HEAD = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


def test_stale_images_flags_missing_and_old(tmp_path):
    created = {"p-gateway": HEAD - timedelta(days=4), "p-niyan-api": HEAD + timedelta(hours=1)}
    missing, old = P.stale_images(
        tmp_path, "p", ["gateway", "niyan-api", "loadtest"],
        head_time=lambda _r: HEAD, image_created=lambda i: created.get(i),
    )
    assert missing == ["p-loadtest"] and old == ["p-gateway"]


def test_stale_images_silent_when_docker_fails(tmp_path):
    def boom(_i):
        raise RuntimeError("no docker")

    assert P.stale_images(tmp_path, "p", ["gateway"], head_time=lambda _r: HEAD, image_created=boom) == ([], [])


def test_stale_images_no_git_only_reports_missing(tmp_path):
    missing, old = P.stale_images(
        tmp_path, "p", ["gateway", "admin-ui"], head_time=lambda _r: None,
        image_created=lambda i: HEAD if i == "p-gateway" else None,
    )
    assert missing == ["p-admin-ui"] and old == []


def test_parse_docker_time():
    assert P._parse_docker_time("2026-10-24T08:35:12.123456789Z") == datetime(2026, 10, 24, 8, 35, 12, tzinfo=timezone.utc)
    assert P._parse_docker_time("garbage") is None


def test_built_services_follow_profiles():
    cfg = NiyanConfig()
    cfg.admin.enabled = False
    cfg.guardrails.enabled = False
    assert built_services(cfg) == ["gateway", "niyan-api", "loadtest"]
    cfg.admin.enabled = True
    assert "admin-ui" in built_services(cfg)


# --- CLI wiring -------------------------------------------------------------

from typer.testing import CliRunner  # noqa: E402

from niyan import main as m  # noqa: E402


class _Down:
    def healthy(self):
        return False


def _cli(tmp_path, monkeypatch, missing=(), old=()):
    repo = _repo(tmp_path, "NIYAN_COMPOSE_PROJECT=proj-y\n")
    monkeypatch.setenv("NIYAN_ROOT", str(repo))
    monkeypatch.delenv("NIYAN_COMPOSE_PROJECT", raising=False)
    monkeypatch.setattr(m, "_repo", lambda: repo)
    monkeypatch.setattr(m, "_load", lambda r: NiyanConfig())
    monkeypatch.setattr(m, "_api", lambda r, login=False: _Down())
    monkeypatch.setattr(P, "stale_images", lambda *a, **k: (list(missing), list(old)))
    monkeypatch.setattr(m, "detect_profile", lambda *a: (_ for _ in ()).throw(SystemExit(0)))
    return repo


def test_status_shows_root_source_and_project(tmp_path, monkeypatch):
    repo = _cli(tmp_path, monkeypatch)
    out = CliRunner().invoke(m.app, ["status"]).output
    assert f"NIYAN_ROOT={repo}" in out
    assert "Compose project: proj-y" in out


def test_up_warns_on_old_images(tmp_path, monkeypatch):
    _cli(tmp_path, monkeypatch, old=["proj-y-gateway"])
    out = CliRunner().invoke(m.app, ["up"]).output
    assert "older than this checkout" in out and "proj-y-gateway" in out
    assert "niyan up --build" in out


def test_up_warns_on_missing_images(tmp_path, monkeypatch):
    _cli(tmp_path, monkeypatch, missing=["proj-y-admin-ui"])
    out = CliRunner().invoke(m.app, ["up"]).output
    assert "not built yet" in out


def test_up_build_skips_image_warning(tmp_path, monkeypatch):
    _cli(tmp_path, monkeypatch, old=["proj-y-gateway"])
    out = CliRunner().invoke(m.app, ["up", "--build"]).output
    assert "older than" not in out
