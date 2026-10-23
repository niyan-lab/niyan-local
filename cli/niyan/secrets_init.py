"""Generate per-install secrets for .env and niyan.yaml (no shared defaults).

Run by install.sh / install.ps1 (``niyan secrets init``). Idempotent: existing
non-default values are kept so re-running the installer never breaks data.
"""

from __future__ import annotations

import os
import re
import secrets
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

# Values that shipped as defaults in earlier builds. Treated as "unset".
INSECURE_VALUES = {
    "",
    "niyan",
    "sk-niyan-local",
    "change-me-niyan-dev-secret",
    "niyan-langfuse-nextauth-secret-change-me",
    "niyan-langfuse-salt-change-me",
    "0" * 64,
}
PLACEHOLDER_RE = re.compile(r"^(__.*__|<.*>|change-?me.*)$", re.I)


def is_insecure(value: str) -> bool:
    v = (value or "").strip().strip("\"'")
    return v in INSECURE_VALUES or bool(PLACEHOLDER_RE.match(v)) or "change-me" in v.lower()


def _hex(n: int) -> str:
    return secrets.token_hex(n)


# .env keys -> generator. Postgres/Langfuse keys guard on-disk data.
ENV_SECRETS = {
    "POSTGRES_PASSWORD": lambda: _hex(24),
    "LANGFUSE_NEXTAUTH_SECRET": lambda: _hex(32),
    "LANGFUSE_SALT": lambda: _hex(32),
    "LANGFUSE_ENCRYPTION_KEY": lambda: _hex(32),  # 64 hex chars = 256-bit
}
DATA_BOUND = set(ENV_SECRETS)


def _pg_volume_exists() -> bool:
    try:
        out = subprocess.run(
            ["docker", "volume", "ls", "-q", "--filter", "name=niyan_niyan_pg"],
            capture_output=True, text=True, timeout=15,
        ).stdout
        return "niyan_niyan_pg" in out.split()
    except Exception:
        return False


def _read_env(path: Path) -> Tuple[List[str], Dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    values: Dict[str, str] = {}
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            values[k.strip()] = v.strip()
    return lines, values


def _set_env(lines: List[str], key: str, value: str) -> List[str]:
    out, done = [], False
    for line in lines:
        s = line.strip()
        if not s.startswith("#") and "=" in s and s.split("=", 1)[0].strip() == key:
            out.append(f"{key}={value}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"{key}={value}")
    return out


def _yaml_section_value(text: str, section: str, key: str) -> Tuple[str, re.Match]:
    m = re.search(
        rf"(?m)^{section}:\n((?:[ \t]+.*\n|[ \t]*\n)*)", text if text.endswith("\n") else text + "\n"
    )
    if not m:
        return "", None
    km = re.search(rf"(?m)^([ \t]+{key}:[ \t]*)(.*)$", m.group(1))
    return (km.group(2).strip().strip("\"'") if km else ""), m


def _yaml_set(text: str, section: str, key: str, value: str) -> str:
    if not text.endswith("\n"):
        text += "\n"
    m = re.search(rf"(?m)^{section}:\n((?:[ \t]+.*\n|[ \t]*\n)*)", text)
    if not m:
        return text + f"\n{section}:\n  {key}: \"{value}\"\n"
    body = m.group(1)
    if re.search(rf"(?m)^[ \t]+{key}:", body):
        body = re.sub(rf"(?m)^([ \t]+{key}:)[ \t]*.*$", lambda mm: f'{mm.group(1)} "{value}"', body, count=1)
    else:
        body = f'  {key}: "{value}"\n' + body
    return text[: m.start(1)] + body + text[m.end(1):]


def _yaml_api_keys(text: str) -> List[str]:
    m = re.search(r"(?m)^proxy:\n((?:[ \t]+.*\n|[ \t]*\n)*)", text)
    if not m:
        return []
    km = re.search(r"(?m)^[ \t]+api_keys:[ \t]*(\[\])?[ \t]*\n((?:[ \t]+-[ \t]*.*\n)*)", m.group(1))
    if not km:
        return []
    return [x.strip().lstrip("-").strip().strip("\"'") for x in km.group(2).splitlines() if x.strip()]


def _yaml_set_api_keys(text: str, keys: List[str]) -> str:
    m = re.search(r"(?m)^proxy:\n((?:[ \t]+.*\n|[ \t]*\n)*)", text)
    items = "".join(f"    - {k}\n" for k in keys)
    if not m:
        return text + f"\nproxy:\n  port: 4000\n  api_keys:\n{items}"
    body = m.group(1)
    new, n = re.subn(
        r"(?m)^([ \t]+)api_keys:[ \t]*(\[\])?[ \t]*\n(?:[ \t]+-[ \t]*.*\n)*",
        lambda mm: f"{mm.group(1)}api_keys:\n{items}", body, count=1,
    )
    if not n:
        new = body + f"  api_keys:\n{items}"
    return text[: m.start(1)] + new + text[m.end(1):]


def ensure_secrets(repo_root: Path) -> Dict[str, List[str]]:
    """Fill missing/default secrets. Returns {'generated': [...], 'kept': [...], 'warnings': [...]}."""
    report: Dict[str, List[str]] = {"generated": [], "kept": [], "warnings": []}
    env_path = repo_root / ".env"
    yaml_path = repo_root / "niyan.yaml"
    pg_exists = None

    lines, values = _read_env(env_path)
    for key, gen in ENV_SECRETS.items():
        cur = values.get(key, "")
        if cur and not is_insecure(cur):
            report["kept"].append(key)
            continue
        if cur and key in DATA_BOUND:
            if pg_exists is None:
                pg_exists = _pg_volume_exists()
            if pg_exists:
                report["warnings"].append(
                    f"{key} is a shipped default but Niyan data volumes exist; kept it to avoid breaking "
                    "data. Run ./uninstall.sh --volumes && ./install.sh to rotate."
                )
                continue
        lines = _set_env(lines, key, gen())
        report["generated"].append(key)
    # These now live in niyan.yaml only (single source for CLI + API).
    lines = [
        l for l in lines
        if l.strip().split("=", 1)[0].strip() not in {"NIYAN_ADMIN_PASSWORD", "NIYAN_JWT_SECRET", "LITELLM_MASTER_KEY"}
    ]
    env_path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    os.chmod(env_path, 0o600)

    text = yaml_path.read_text(encoding="utf-8") if yaml_path.exists() else ""
    for key, gen in (("password", lambda: secrets.token_urlsafe(18)), ("jwt_secret", lambda: _hex(32))):
        cur, _ = _yaml_section_value(text, "admin_auth", key)
        if cur and not is_insecure(cur):
            report["kept"].append(f"admin_auth.{key}")
        else:
            text = _yaml_set(text, "admin_auth", key, gen())
            report["generated"].append(f"admin_auth.{key}")
    keys = [k for k in _yaml_api_keys(text) if not is_insecure(k)]
    if keys:
        report["kept"].append("proxy.api_keys")
    else:
        keys = [f"sk-niyan-{_hex(24)}"]
        report["generated"].append("proxy.api_keys")
    text = _yaml_set_api_keys(text, keys)
    yaml_path.write_text(text, encoding="utf-8")
    os.chmod(yaml_path, 0o600)
    return report


def check_secrets(env: Dict[str, str]) -> List[str]:
    """Names of secrets in a Compose env that are empty or shipped defaults."""
    names = ["NIYAN_ADMIN_PASSWORD", "NIYAN_JWT_SECRET", "LITELLM_MASTER_KEY", *ENV_SECRETS]
    return [n for n in names if is_insecure(env.get(n, ""))]
