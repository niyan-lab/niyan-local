"""Basic config schema tests (no Docker required)."""

from unittest.mock import patch

from niyan.config import Profile, load_config, uses_host_ollama
from niyan.doctor import detect_profile
from niyan.local_compose import compose_cmd, compose_files, find_repo_root, guardrails_url
from niyan.shell_init import build_block, detect_shell, remove_init, remove_legacy_init
from niyan.uninstall import run_uninstall


def test_load_example_config():
    root = find_repo_root()
    cfg = load_config(root / "configs" / "niyan.example.yaml")
    assert cfg.proxy.port == 4000
    assert any(m.id.startswith("llama") for m in cfg.models)
    assert cfg.guardrails.provider.value == "llm_guard"
    assert "prompt_injection" in cfg.guardrails.llm_guard.scanners
    assert "pii" in cfg.guardrails.llm_guard.output_scanners
    assert cfg.embeddings.model == "nomic-embed-text"
    assert cfg.vector.enabled is False
    assert cfg.vector.provider.value == "qdrant"


def test_compose_includes_profiles():
    root = find_repo_root()
    cfg = load_config(root / "configs" / "niyan.example.yaml")
    profile = detect_profile(cfg.profile)
    cmd = compose_cmd(root, profile, cfg)
    assert "docker" in cmd[0]
    assert "--profile" in cmd
    assert guardrails_url(cfg).endswith(":8088")
    assert "vector-qdrant" not in cmd
    assert "vector-pg" not in cmd


def test_compose_vector_profiles():
    from niyan.config import VectorProvider

    root = find_repo_root()
    cfg = load_config(root / "configs" / "niyan.example.yaml")
    cfg.vector.enabled = True
    cfg.vector.provider = VectorProvider.qdrant
    profile = detect_profile(cfg.profile)
    cmd = compose_cmd(root, profile, cfg)
    assert "vector-qdrant" in cmd
    cfg.vector.provider = VectorProvider.pgvector
    cmd = compose_cmd(root, profile, cfg)
    assert "vector-pg" in cmd
    assert "vector-qdrant" not in cmd


def test_detect_profile_windows():
    with patch("niyan.doctor.platform.system", return_value="Windows"):
        assert detect_profile(Profile.auto) == Profile.windows


def test_detect_profile_mac():
    with patch("niyan.doctor.platform.system", return_value="Darwin"):
        assert detect_profile(Profile.auto) == Profile.mac


def test_windows_uses_host_ollama_overlay():
    root = find_repo_root()
    cfg = load_config(root / "configs" / "niyan.example.yaml")
    assert uses_host_ollama(Profile.windows)
    files = compose_files(root, Profile.windows)
    assert any(f.name == "docker-compose.host-ollama.yml" for f in files)
    cmd = compose_cmd(root, Profile.windows, cfg)
    assert "ollama" not in [cmd[i + 1] for i, x in enumerate(cmd) if x == "--profile"]


def test_powershell_shell_block():
    root = find_repo_root()
    block = build_block(root, "powershell")
    assert "NIYAN_ROOT" in block
    assert "niyan.ps1" in block
    assert detect_shell("pwsh") == "powershell"


def test_remove_niyan_shell_block(tmp_path):
    rc = tmp_path / ".zshrc"
    rc.write_text(
        "# before\n"
        "# >>> niyan initialize >>>\n"
        'export NIYAN_ROOT="/repo"\n'
        "# <<< niyan initialize <<<\n"
        "# after\n",
        encoding="utf-8",
    )
    assert remove_init(rc) is True
    text = rc.read_text(encoding="utf-8")
    assert "niyan initialize" not in text
    assert "# before" in text
    assert "# after" in text


def test_run_uninstall_removes_venv_and_config(tmp_path):
    repo = tmp_path / "niyan-local"
    (repo / "cli").mkdir(parents=True)
    (repo / ".venv" / "bin").mkdir(parents=True)
    (repo / ".venv" / "bin" / "niyan").write_text("#!/bin/sh\n", encoding="utf-8")
    (repo / "niyan.yaml").write_text("proxy: {}\n", encoding="utf-8")
    (repo / ".env").write_text("X=1\n", encoding="utf-8")
    (repo / "services" / "litellm").mkdir(parents=True)
    (repo / "services" / "litellm" / "config.generated.yaml").write_text("x: 1\n", encoding="utf-8")

    with patch("niyan.uninstall.load_config", side_effect=RuntimeError("no docker")), patch(
        "niyan.uninstall.init_shell", return_value=("removed", tmp_path / ".zshrc")
    ):
        notes = run_uninstall(repo, volumes=False, keep_config=False)

    assert not (repo / ".venv").exists()
    assert not (repo / "niyan.yaml").exists()
    assert not (repo / ".env").exists()
    assert not (repo / "services" / "litellm" / "config.generated.yaml").exists()
    assert any("left checkout" in n for n in notes)


def test_remove_legacy_novus_shell_block(tmp_path):
    rc = tmp_path / ".zshrc"
    rc.write_text(
        "# before\n"
        "# >>> novus initialize >>>\n"
        'export NOVUS_ROOT="/repo"\n'
        '. "/repo/shell/novus.sh"\n'
        "# <<< novus initialize <<<\n"
        "# after\n",
        encoding="utf-8",
    )
    assert remove_legacy_init(rc) is True
    text = rc.read_text(encoding="utf-8")
    assert "novus" not in text
    assert "# before" in text
    assert "# after" in text
