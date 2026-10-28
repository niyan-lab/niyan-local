"""Detect admin password drift between niyan.yaml and .env.

niyan.yaml admin_auth is the single source (the CLI logs in with it and
`niyan up` injects it into niyan-api). `niyan secrets init` removes
NIYAN_ADMIN_PASSWORD from .env, but a hand-edited .env (or one from an old
install) can bring it back; plain `docker compose up` would then start the API
with a different password than the CLI uses. Values are compared as SHA-256
digests in constant time and never printed.
"""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
from typing import Optional

ENV_KEY = "NIYAN_ADMIN_PASSWORD"


def _digest(v: str) -> bytes:
    return hashlib.sha256(v.encode("utf-8")).digest()


def _env_value(env_path: Path, key: str) -> Optional[str]:
    if not env_path.exists():
        return None
    found = None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            if k.strip() == key:
                found = v.strip().strip("\"'")
    return found


def admin_password_drift(repo: Path, yaml_password: str) -> bool:
    """True if .env sets NIYAN_ADMIN_PASSWORD to something other than niyan.yaml."""
    env_val = _env_value(Path(repo) / ".env", ENV_KEY)
    if env_val is None or env_val == "":
        return False
    return not hmac.compare_digest(_digest(env_val), _digest(yaml_password or ""))


DRIFT_WARNING = (
    "[yellow]Warning: .env NIYAN_ADMIN_PASSWORD differs from niyan.yaml admin_auth.password. "
    "niyan.yaml is the source of truth (the CLI and `niyan up` use it); remove the "
    ".env line (or run `niyan secrets init`) so a plain `docker compose up` cannot "
    "start niyan-api with a different password.[/yellow]"
)
