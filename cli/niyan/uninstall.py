"""Remove a from-source Niyan install (venv, shell hook, optional Docker volumes)."""

from __future__ import annotations

import shutil
from pathlib import Path

from niyan.config import load_config
from niyan.local_compose import stack_down
from niyan.shell_init import init_shell


def run_uninstall(
    repo: Path,
    *,
    volumes: bool = False,
    keep_config: bool = False,
    defer_venv: bool = False,
) -> list[str]:
    """Best-effort uninstall.

    ``defer_venv``: leave ``.venv`` for the caller to delete *after* it has finished
    printing. The CLI runs from that venv and rich lazily imports modules such as
    ``rich._emoji_codes`` on first markup render; deleting the venv first made the
    final ``console.print`` crash with ``ModuleNotFoundError``.
    """
    notes: list[str] = []
    yaml_path = repo / "niyan.yaml"
    if yaml_path.exists():
        try:
            cfg = load_config(yaml_path)
            stack_down(repo, cfg, volumes=volumes)
            notes.append(
                "stopped Compose stack" + (" and deleted volumes" if volumes else "")
            )
        except Exception as exc:  # pragma: no cover — best-effort when Docker is down
            notes.append(f"stack stop skipped: {exc}")
    else:
        notes.append("no niyan.yaml — skipped Compose down")

    action, rc = init_shell(repo, reverse=True)
    notes.append(f"shell hook {action}: {rc}")

    venv = repo / ".venv"
    if venv.exists():
        if defer_venv:
            notes.append(f"removing {venv}")
        else:
            shutil.rmtree(venv)
            notes.append(f"removed {venv}")

    generated = repo / "services" / "litellm" / "config.generated.yaml"
    if generated.exists():
        generated.unlink()
        notes.append("removed LiteLLM generated config")

    if not keep_config:
        for name in ("niyan.yaml", ".env"):
            path = repo / name
            if path.exists():
                path.unlink()
                notes.append(f"removed {path.name}")

    notes.append(f"left checkout in place: {repo}")
    return notes
