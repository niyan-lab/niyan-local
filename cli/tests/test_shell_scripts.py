"""Shell-level checks (bash; no Docker needed)."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(not BASH, reason="bash not available")

GOOD = {
    "NIYAN_ADMIN_PASSWORD": "Q" * 24, "NIYAN_JWT_SECRET": "a" * 64, "LITELLM_MASTER_KEY": "sk-niyan-" + "b" * 48,
    "POSTGRES_PASSWORD": "c" * 48, "LANGFUSE_NEXTAUTH_SECRET": "d" * 64, "LANGFUSE_SALT": "e" * 64,
    "LANGFUSE_ENCRYPTION_KEY": "f" * 64,
}


def _check(tmp_path, env_values):
    stack = tmp_path / "stack"
    stack.mkdir(parents=True, exist_ok=True)
    (stack / "docker-compose.yml").write_text("services: {}\n")
    (stack / ".env").write_text("".join(f"{k}={v}\n" for k, v in env_values.items()))
    lib = tmp_path / "niyan_lib.sh"  # bash 3.2: no `source <(...)`
    lib.write_text("\n".join(l for l in (ROOT / "bootstrap/bin/niyan").read_text().splitlines() if l.strip() != 'main "$@"'))
    script = f'source "{lib}"; check_secrets'
    env = {**os.environ, "NIYAN_HOME": str(tmp_path)}
    return subprocess.run([BASH, "-c", script], capture_output=True, text=True, env=env)


def test_bootstrap_up_precheck_refuses_defaults(tmp_path):
    r = _check(tmp_path, {**GOOD, "POSTGRES_PASSWORD": "niyan", "LITELLM_MASTER_KEY": "sk-niyan-local"})
    assert r.returncode != 0
    assert "POSTGRES_PASSWORD" in r.stderr and "LITELLM_MASTER_KEY" in r.stderr


def test_bootstrap_up_precheck_accepts_strong_and_legacy_marker(tmp_path):
    assert _check(tmp_path, GOOD).returncode == 0, _check(tmp_path, GOOD).stderr
    legacy = {**GOOD, "LANGFUSE_ENCRYPTION_KEY": "0" * 64, "NIYAN_LEGACY_LANGFUSE_ENCRYPTION_KEY": "1"}
    assert _check(tmp_path, legacy).returncode == 0


@pytest.mark.parametrize("f", ["install.sh", "uninstall.sh", "bootstrap/install.sh", "bootstrap/bin/niyan",
                               "scripts/smoke_test.sh", "scripts/rag_smoke_test.sh"])
def test_shell_syntax(f):
    assert subprocess.run([BASH, "-n", str(ROOT / f)]).returncode == 0
