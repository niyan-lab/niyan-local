"""Compose project name and repo-root diagnostics.

Containers, built images (``<project>-<service>``) and volumes
(``<project>_niyan_pg`` …) are all scoped by the Compose project name, so two
checkouts with the same name share (and overwrite) each other's stack.

Resolution order for the project name:

1. ``NIYAN_COMPOSE_PROJECT`` in the process environment
2. ``NIYAN_COMPOSE_PROJECT=`` in the checkout's ``.env``
3. an existing ``.env`` without that key -> ``niyan`` (installs made before the
   key existed ran as ``niyan``; keep their containers and Postgres data)
4. otherwise this repo's default (new installs get it via ``.env.example``)
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, Tuple

ENV_KEY = "NIYAN_COMPOSE_PROJECT"
LEGACY_PROJECT = "niyan"
DEFAULT_PROJECT = "niyan"
_VALID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _env_file_value(env_path: Path, key: str) -> Optional[str]:
    if not env_path.exists():
        return None
    found = None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        if k.strip() == key:
            found = v.strip().strip('"').strip("'")
    return found


def compose_project(repo_root: Path, environ: Optional[dict] = None) -> Tuple[str, str]:
    """Return (project_name, source)."""
    env = os.environ if environ is None else environ
    explicit = (env.get(ENV_KEY) or "").strip()
    if explicit:
        name, source = explicit, f"{ENV_KEY} (environment)"
    else:
        env_path = repo_root / ".env"
        from_file = _env_file_value(env_path, ENV_KEY)
        if from_file:
            name, source = from_file, f"{ENV_KEY} in .env"
        elif env_path.exists():
            name, source = LEGACY_PROJECT, f".env has no {ENV_KEY} (pre-existing install)"
        else:
            name, source = DEFAULT_PROJECT, "default"
    if not _VALID.match(name):
        raise ValueError(
            f"invalid {ENV_KEY}={name!r}: use lowercase letters, digits, '-' or '_'"
        )
    return name, source


def project_name(repo_root: Path) -> str:
    return compose_project(repo_root)[0]


def pg_volume(project: str) -> str:
    return f"{project}_niyan_pg"


def repo_root_source(repo_root: Path, environ: Optional[dict] = None, cwd: Optional[Path] = None) -> str:
    """Explain why find_repo_root() picked repo_root (mirrors its order)."""
    env = os.environ if environ is None else environ
    resolved = repo_root.resolve()
    for key in ("NIYAN_ROOT", "NIYAN_HOME"):
        val = env.get(key)
        if val and Path(val).expanduser().resolve() == resolved:
            return f"{key}={val}"
    here = (cwd or Path.cwd()).resolve()
    if here == resolved or resolved in here.parents:
        return "current directory"
    return "CLI install location (no NIYAN_ROOT/NIYAN_HOME, cwd outside a checkout)"


# --- stale image check -----------------------------------------------------

BUILT_SERVICES = ("gateway", "niyan-api", "admin-ui", "guardrails", "nemo-guardrails", "loadtest")


def _git_head_time(repo_root: Path) -> Optional[datetime]:
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "log", "-1", "--format=%ct"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return None
    if r.returncode != 0 or not r.stdout.strip().isdigit():
        return None
    return datetime.fromtimestamp(int(r.stdout.strip()), tz=timezone.utc)


def _parse_docker_time(s: str) -> Optional[datetime]:
    s = s.strip()
    if not s:
        return None
    m = re.match(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.\d+)?(Z|[+-]\d\d:\d\d)?$", s)
    if not m:
        return None
    tz = m.group(3) or "Z"
    tz = "+00:00" if tz == "Z" else tz
    try:
        return datetime.fromisoformat(m.group(1) + tz)
    except ValueError:
        return None


def _image_created(image: str) -> Optional[datetime]:
    """Image creation time; None when missing. Raises on docker failure."""
    r = subprocess.run(
        ["docker", "image", "inspect", "-f", "{{.Created}}", image],
        capture_output=True, text=True, timeout=20,
    )
    if r.returncode != 0:
        if "No such image" in (r.stderr or "") or "no such image" in (r.stderr or "").lower():
            return None
        raise RuntimeError("docker image inspect failed")
    return _parse_docker_time(r.stdout)


def stale_images(
    repo_root: Path,
    project: str,
    services: List[str],
    *,
    head_time: Callable[[Path], Optional[datetime]] = _git_head_time,
    image_created: Callable[[str], Optional[datetime]] = _image_created,
) -> Tuple[List[str], List[str]]:
    """Return (missing, older_than_head) image names for locally built services."""
    head = head_time(repo_root)
    missing: List[str] = []
    old: List[str] = []
    for svc in services:
        image = f"{project}-{svc}"
        try:
            created = image_created(image)
        except Exception:
            return [], []  # docker unavailable: say nothing
        if created is None:
            missing.append(image)
        elif head is not None and created < head:
            old.append(image)
    return missing, old
