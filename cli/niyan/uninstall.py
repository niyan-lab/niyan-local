"""Remove a from-source Niyan install (venv, shell hook, optional Docker volumes)."""

from __future__ import annotations

import shutil
from pathlib import Path

from niyan.config import load_config
from niyan.local_compose import stack_down
from niyan.shell_init import init_shell

# Exit code used by `niyan uninstall` when Compose could not stop the stack.
# uninstall.sh / uninstall.ps1 treat it as "nothing changed, do not fall back".
EXIT_COMPOSE_FAILED = 3


EXIT_NO_CONFIG = 4


class ComposeDownFailed(RuntimeError):
    """Compose could not stop the stack; nothing was removed."""


class MissingConfig(RuntimeError):
    """niyan.yaml is gone, so the CLI cannot build the Compose command; nothing was removed."""


def run_uninstall(
    repo: Path,
    *,
    volumes: bool = False,
    keep_config: bool = False,
    defer_venv: bool = False,
) -> list[str]:
    """Uninstall a from-source checkout.

    Stopping the stack comes first. If Compose fails (Docker down, compose error),
    ``ComposeDownFailed`` is raised before anything is removed, so the user can
    start Docker and re-run with niyan.yaml, .env and .venv intact.

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
            rc = stack_down(repo, cfg, volumes=volumes)
        except Exception as exc:
            raise ComposeDownFailed(f"could not stop the Compose stack: {exc}") from exc
        if rc != 0:
            raise ComposeDownFailed(f"docker compose down exited {rc}")
        notes.append(
            "stopped Compose stack" + (" and deleted volumes" if volumes else "")
        )
    else:
        # Containers may still be running; ./uninstall.sh's fallback stops them
        # with the default project and every profile.
        raise MissingConfig("niyan.yaml not found; cannot stop the stack from the CLI")

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
