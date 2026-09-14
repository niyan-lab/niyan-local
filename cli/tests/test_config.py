"""Basic config schema tests (no Docker required)."""

from unittest.mock import patch

from niyan.config import Profile, load_config, uses_host_ollama
from niyan.doctor import detect_profile
from niyan.local_compose import compose_cmd, compose_files, find_repo_root, guardrails_url
from niyan.shell_init import build_block, detect_shell


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

