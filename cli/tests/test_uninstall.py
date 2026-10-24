import pytest

from niyan import uninstall as u


def test_defer_venv_keeps_running_venv(tmp_path, monkeypatch):
    (tmp_path / "niyan.yaml").write_text("profile: auto\n")
    monkeypatch.setattr(u, "init_shell", lambda repo, reverse=False: ("removed", tmp_path / ".zshrc"))
    monkeypatch.setattr(u, "load_config", lambda p: object())
    monkeypatch.setattr(u, "stack_down", lambda repo, cfg, volumes=False: 0)
    (tmp_path / ".venv").mkdir()
    notes = u.run_uninstall(tmp_path, defer_venv=True, keep_config=True)
    assert (tmp_path / ".venv").exists()
    assert any("removing" in n for n in notes)
    u.run_uninstall(tmp_path, keep_config=True)
    assert not (tmp_path / ".venv").exists()


def _repo_with_install(tmp_path):
    (tmp_path / "niyan.yaml").write_text("profile: auto\n")
    (tmp_path / ".env").write_text("X=1\n")
    (tmp_path / ".venv").mkdir()
    return tmp_path


def _no_shell(monkeypatch, calls):
    def fake(repo, reverse=False):
        calls.append("shell")
        return ("removed", repo / ".zshrc")

    monkeypatch.setattr(u, "init_shell", fake)
    monkeypatch.setattr(u, "load_config", lambda p: object())


@pytest.mark.parametrize("failure", ["rc", "raise"])
def test_compose_failure_removes_nothing(tmp_path, monkeypatch, failure):
    repo = _repo_with_install(tmp_path)
    calls: list[str] = []
    _no_shell(monkeypatch, calls)

    def down(repo, cfg, volumes=False):
        if failure == "raise":
            raise FileNotFoundError("docker")
        return 1

    monkeypatch.setattr(u, "stack_down", down)
    with pytest.raises(u.ComposeDownFailed):
        u.run_uninstall(repo)
    assert (repo / "niyan.yaml").exists()
    assert (repo / ".env").exists()
    assert (repo / ".venv").exists()
    assert calls == []  # shell hook untouched


def test_compose_success_removes_install(tmp_path, monkeypatch):
    repo = _repo_with_install(tmp_path)
    calls: list[str] = []
    _no_shell(monkeypatch, calls)
    monkeypatch.setattr(u, "stack_down", lambda repo, cfg, volumes=False: 0)
    u.run_uninstall(repo)
    assert not (repo / "niyan.yaml").exists()
    assert not (repo / ".env").exists()
    assert not (repo / ".venv").exists()
    assert calls == ["shell"]


def test_cli_exits_3_on_compose_failure(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from niyan import main as m

    repo = _repo_with_install(tmp_path)
    monkeypatch.setattr(m, "_repo", lambda: repo)

    def boom(*a, **k):
        raise u.ComposeDownFailed("docker compose down exited 1")

    monkeypatch.setattr(m, "run_uninstall", boom)
    result = CliRunner().invoke(m.app, ["uninstall", "--yes"])
    assert result.exit_code == u.EXIT_COMPOSE_FAILED == 3
    assert "Nothing was removed" in result.output
    assert "Uninstalled" not in result.output
    assert (repo / ".venv").exists()


def test_missing_yaml_removes_nothing(tmp_path, monkeypatch):
    calls: list[str] = []
    _no_shell(monkeypatch, calls)
    (tmp_path / ".env").write_text("X=1\n")
    (tmp_path / ".venv").mkdir()
    with pytest.raises(u.MissingConfig):
        u.run_uninstall(tmp_path)
    assert (tmp_path / ".env").exists() and (tmp_path / ".venv").exists()
    assert calls == []
