from niyan import uninstall as u


def test_defer_venv_keeps_running_venv(tmp_path, monkeypatch):
    monkeypatch.setattr(u, "init_shell", lambda repo, reverse=False: ("removed", tmp_path / ".zshrc"))
    (tmp_path / ".venv").mkdir()
    notes = u.run_uninstall(tmp_path, defer_venv=True)
    assert (tmp_path / ".venv").exists()
    assert any("removing" in n for n in notes)
    u.run_uninstall(tmp_path)
    assert not (tmp_path / ".venv").exists()
