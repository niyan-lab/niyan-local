"""Generate per-install secrets for .env and niyan.yaml (no shared defaults).

Run by install.sh / install.ps1 (``niyan secrets init``). Idempotent: existing
non-default values are kept. Upgrades from old default installs are migrated
in place (never wiping data):

* POSTGRES_PASSWORD default/missing + existing volume -> new password applied
  with ``ALTER USER`` over the container's local socket, verified over TCP,
  then written to .env.
* LANGFUSE_SALT / LANGFUSE_ENCRYPTION_KEY default/missing + Langfuse rows that
  depend on them -> kept (rotating would break API keys / encrypted LLM keys),
  flagged with NIYAN_LEGACY_LANGFUSE_* markers and a loud warning. Rotated
  when no dependent rows exist. NEXTAUTH_SECRET is always rotatable.
* Docker unreachable while a data-bound secret needs work -> fail closed,
  nothing is written.
"""

from __future__ import annotations

import os
import re
import secrets
import subprocess
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from niyan.secrets_policy import INSECURE_VALUES, is_insecure  # noqa: F401  (re-export)

PG_VOLUME = "niyan_niyan_pg"
LEGACY_MARKERS = {
    "LANGFUSE_SALT": "NIYAN_LEGACY_LANGFUSE_SALT",
    "LANGFUSE_ENCRYPTION_KEY": "NIYAN_LEGACY_LANGFUSE_ENCRYPTION_KEY",
}
# What old builds used when the .env key was absent (compose ${VAR:-default}).
OLD_COMPOSE_DEFAULTS = {
    "POSTGRES_PASSWORD": "niyan",
    "LANGFUSE_NEXTAUTH_SECRET": "niyan-langfuse-nextauth-secret-change-me",
    "LANGFUSE_SALT": "niyan-langfuse-salt-change-me",
    "LANGFUSE_ENCRYPTION_KEY": "0" * 64,
}
# Langfuse tables whose rows depend on the secret (to_regclass-guarded).
LANGFUSE_DEPENDENTS = {
    "LANGFUSE_SALT": ["api_keys"],
    "LANGFUSE_ENCRYPTION_KEY": ["llm_api_keys", "blob_storage_integrations", "posthog_integrations"],
}


class SecretsInitError(RuntimeError):
    """Refused to change secrets (fail closed)."""


def _hex(n: int) -> str:
    return secrets.token_hex(n)


# .env keys -> generator. Postgres/Langfuse keys guard on-disk data.
ENV_SECRETS = {
    "POSTGRES_PASSWORD": lambda: _hex(24),
    "LANGFUSE_NEXTAUTH_SECRET": lambda: _hex(32),
    "LANGFUSE_SALT": lambda: _hex(32),
    "LANGFUSE_ENCRYPTION_KEY": lambda: _hex(32),  # 64 hex chars = 256-bit
}
DATA_BOUND = {"POSTGRES_PASSWORD", "LANGFUSE_SALT", "LANGFUSE_ENCRYPTION_KEY"}
ADMIN_PASSWORD_LEN = 24


def new_admin_password() -> str:
    return secrets.token_urlsafe(ADMIN_PASSWORD_LEN)[:ADMIN_PASSWORD_LEN]


# ---------------------------------------------------------------- file io

def write_private(path: Path, text: str) -> None:
    """Write with mode 0600 from creation (no world-readable window)."""
    path = Path(path)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _read_env(path: Path) -> Tuple[List[str], Dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    values: Dict[str, str] = {}
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            values[k.strip()] = v.strip().strip("\"'")
    return lines, values


def _set_env(lines: List[str], key: str, value: str) -> List[str]:
    out, done = [], False
    for line in lines:
        s = line.strip()
        if not s.startswith("#") and "=" in s and s.split("=", 1)[0].strip() == key:
            if not done:
                out.append(f"{key}={value}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"{key}={value}")
    return out


def _del_env(lines: List[str], key: str) -> List[str]:
    return [l for l in lines if l.strip().startswith("#") or l.strip().split("=", 1)[0].strip() != key]


def _write_env(path: Path, lines: List[str]) -> None:
    write_private(path, "\n".join(lines).rstrip("\n") + "\n")


# ---------------------------------------------------------------- yaml (text-preserving)

def _section(text: str, section: str) -> Optional[re.Match]:
    return re.search(rf"(?m)^{re.escape(section)}:[ \t]*(?:#.*)?\n((?:[ \t]+.*\n|[ \t]*\n)*)", text)


def _scalar(raw: str) -> str:
    v = raw.strip()
    if v[:1] in {'"', "'"}:
        q = v[0]
        end = v.find(q, 1)
        return v[1:end] if end > 0 else v[1:]
    return re.split(r"[ \t]+#", v, maxsplit=1)[0].strip()


def _indent(body: str) -> str:
    m = re.search(r"(?m)^([ \t]+)\S", body)
    return m.group(1) if m else "  "


def _norm(text: str) -> Tuple[str, str]:
    nl = "\r\n" if "\r\n" in text else "\n"
    text = text.replace("\r\n", "\n")
    if text and not text.endswith("\n"):
        text += "\n"
    return text, nl


def _yaml_section_value(text: str, section: str, key: str) -> Tuple[str, Optional[re.Match]]:
    text, _ = _norm(text)
    m = _section(text, section)
    if not m:
        return "", None
    km = re.search(rf"(?m)^[ \t]+{re.escape(key)}:[ \t]*(.*)$", m.group(1))
    return (_scalar(km.group(1)) if km else ""), m


def _yaml_set(text: str, section: str, key: str, value: str) -> str:
    text, nl = _norm(text)
    m = _section(text, section)
    if not m:
        out = text + f"\n{section}:\n  {key}: \"{value}\"\n"
    else:
        body = m.group(1)
        if re.search(rf"(?m)^[ \t]+{re.escape(key)}:", body):
            body = re.sub(
                rf"(?m)^([ \t]+{re.escape(key)}:)[ \t]*.*$", lambda mm: f'{mm.group(1)} "{value}"', body, count=1
            )
        else:
            body = f'{_indent(body)}{key}: "{value}"\n' + body
        out = text[: m.start(1)] + body + text[m.end(1):]
    return out.replace("\n", nl) if nl != "\n" else out


_API_KEYS_RE = r"(?m)^([ \t]+)api_keys:[ \t]*(\[[^\]\n]*\])?[ \t]*(?:#.*)?\n((?:\1[ \t]*-[ \t]*.*\n|[ \t]*#.*\n)*)"


def _yaml_api_keys(text: str) -> List[str]:
    text, _ = _norm(text)
    m = _section(text, "proxy")
    if not m:
        return []
    km = re.search(_API_KEYS_RE, m.group(1))
    if not km:
        return []
    if km.group(2):
        inner = km.group(2)[1:-1]
        return [_scalar(x) for x in inner.split(",") if _scalar(x)]
    items = []
    for x in km.group(3).splitlines():
        s = x.strip()
        if s.startswith("-"):
            v = _scalar(s[1:])
            if v:
                items.append(v)
    return items


def _yaml_set_api_keys(text: str, keys: List[str]) -> str:
    text, nl = _norm(text)
    m = _section(text, "proxy")
    if not m:
        items = "".join(f"    - {k}\n" for k in keys)
        out = text + f"\nproxy:\n  port: 4000\n  api_keys:\n{items}"
    else:
        body = m.group(1)

        def repl(mm: re.Match) -> str:
            ind = mm.group(1)
            return f"{ind}api_keys:\n" + "".join(f"{ind}  - {k}\n" for k in keys)

        new, n = re.subn(_API_KEYS_RE, repl, body, count=1)
        if not n:
            ind = _indent(body)
            new = body + f"{ind}api_keys:\n" + "".join(f"{ind}  - {k}\n" for k in keys)
        out = text[: m.start(1)] + new + text[m.end(1):]
    return out.replace("\n", nl) if nl != "\n" else out


# ---------------------------------------------------------------- docker

def _run(cmd: List[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=kw.pop("timeout", 60), **kw)


def docker_up() -> bool:
    try:
        return _run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=20).returncode == 0
    except Exception:
        return False


def pg_volume_exists() -> Optional[bool]:
    """True/False, or None when Docker can't be asked (unknown -> caller fails closed)."""
    if not docker_up():
        return None
    try:
        r = _run(["docker", "volume", "inspect", PG_VOLUME], timeout=20)
    except Exception:
        return None
    return r.returncode == 0


class PgMigrator:
    """Runs psql inside the niyan postgres container (local socket = trust)."""

    def __init__(self, repo_root: Path, env_values: Dict[str, str]):
        self.repo = repo_root
        self.user = env_values.get("POSTGRES_USER") or "niyan"
        env = os.environ.copy()
        env.update({k: v for k, v in env_values.items() if v})
        from niyan.local_compose import placeholder_env

        self.env = placeholder_env(env)
        self.env["NIYAN_ROOT"] = str(repo_root.resolve())
        self.base = ["docker", "compose", "--project-name", "niyan", "-f", str(repo_root / "deploy" / "docker-compose.yml")]

    def start(self) -> None:
        r = _run(self.base + ["up", "-d", "--no-deps", "postgres"], cwd=str(self.repo), env=self.env, timeout=300)
        if r.returncode != 0:
            raise SecretsInitError("could not start postgres for migration: " + (r.stderr or r.stdout)[-400:])
        import time

        for _ in range(60):
            p = self.exec(["pg_isready", "-U", self.user], check=False)
            if p.returncode == 0:
                # pg_isready can pass during the init-scripts phase; confirm a query works
                if self.psql("postgres", "select 1", check=False).returncode == 0:
                    return
            time.sleep(2)
        raise SecretsInitError("postgres did not become ready for migration")

    def exec(self, args: List[str], stdin: Optional[str] = None, check: bool = True) -> subprocess.CompletedProcess:
        r = _run(self.base + ["exec", "-T", "postgres", *args], cwd=str(self.repo), env=self.env, input=stdin, timeout=120)
        if check and r.returncode != 0:
            raise SecretsInitError(f"postgres command failed: {(r.stderr or '')[-300:]}")
        return r

    def psql(self, db: str, sql: str, check: bool = True) -> subprocess.CompletedProcess:
        return self.exec(["psql", "-v", "ON_ERROR_STOP=1", "-qtA", "-U", self.user, "-d", db], stdin=sql, check=check)

    def rotate_password(self, new: str) -> None:
        assert re.fullmatch(r"[0-9a-f]+", new)
        self.psql("postgres", f'ALTER USER "{self.user}" WITH PASSWORD \'{new}\';\n')
        # Verify over TCP with password auth. 127.0.0.1 is `trust` in the image's
        # pg_hba, so connect to the container's own network IP (scram). The
        # password goes via stdin, never argv.
        r = self.exec(
            ["sh", "-c", 'read -r P; H="$(hostname -i | cut -d" " -f1)"; '
             f'PGPASSWORD="$P" psql -h "$H" -U {self.user} -d postgres -qtAc "select 1"'],
            stdin=new + "\n", check=False,
        )
        if r.returncode != 0 or "1" not in r.stdout:
            raise SecretsInitError("ALTER USER ran but TCP login with the new password failed")

    def count_rows(self, db: str, tables: List[str]) -> Optional[int]:
        parts = [
            f"(case when to_regclass('public.{t}') is null then 0 else "
            f"(xpath('/row/c/text()', query_to_xml('select count(*) as c from public.{t}', false, true, '')))[1]::text::int end)"
            for t in tables
        ]
        r = self.psql(db, "select " + " + ".join(parts) + ";", check=False)
        if r.returncode != 0:
            if "does not exist" in (r.stderr or ""):
                return 0  # database never created
            return None
        try:
            return int(r.stdout.strip().splitlines()[-1])
        except Exception:
            return None


# ---------------------------------------------------------------- main entry

def ensure_secrets(
    repo_root: Path,
    *,
    volume_probe: Callable[[], Optional[bool]] = pg_volume_exists,
    migrator_factory: Callable[[Path, Dict[str, str]], "PgMigrator"] = PgMigrator,
) -> Dict[str, List[str]]:
    """Fill missing/default secrets.

    Returns {'generated', 'kept', 'rotated', 'warnings'}. Raises SecretsInitError
    (writing nothing) when a data-bound secret needs work but Docker is unknown.
    """
    report: Dict[str, List[str]] = {"generated": [], "kept": [], "rotated": [], "warnings": []}
    env_path = repo_root / ".env"
    yaml_path = repo_root / "niyan.yaml"

    lines, values = _read_env(env_path)

    def legacy_ok(key: str) -> bool:
        m = LEGACY_MARKERS.get(key)
        return bool(m and values.get(m) == "1" and values.get(key))

    todo = [k for k in ENV_SECRETS if is_insecure(values.get(k, "")) and not legacy_ok(k)]
    for k in ENV_SECRETS:
        if k not in todo:
            report["kept"].append(k)

    vol: Optional[bool] = False
    if any(k in DATA_BOUND for k in todo):
        vol = volume_probe()
        if vol is None:
            raise SecretsInitError(
                "Docker is not reachable, so it is unknown whether Niyan's Postgres volume exists. "
                "Refusing to generate data-bound secrets (" + ", ".join(k for k in todo if k in DATA_BOUND)
                + "). Start Docker and re-run ./install.sh. Nothing was changed."
            )

    new_env: Dict[str, str] = {}
    mig = None
    if vol:
        mig = migrator_factory(repo_root, {**values, **{k: values.get(k) or OLD_COMPOSE_DEFAULTS[k] for k in todo}})
        mig.start()
    for key in todo:
        gen = ENV_SECRETS[key]
        if not vol or key == "LANGFUSE_NEXTAUTH_SECRET":
            new_env[key] = gen()
            report["generated"].append(key)
            continue
        if key == "POSTGRES_PASSWORD":
            pw = gen()
            mig.rotate_password(pw)
            # Persist immediately: the DB now only accepts the new password.
            lines = _set_env(lines, key, pw)
            _write_env(env_path, lines)
            report["rotated"].append(key)
            continue
        n = mig.count_rows(values.get("POSTGRES_DB") or "langfuse", LANGFUSE_DEPENDENTS[key])
        if n == 0:
            new_env[key] = gen()
            report["rotated"].append(key)
            continue
        legacy = values.get(key) or OLD_COMPOSE_DEFAULTS[key]
        new_env[key] = legacy
        new_env[LEGACY_MARKERS[key]] = "1"
        report["kept"].append(key)
        report["warnings"].append(
            f"{key} is still the old shipped default because existing Langfuse data depends on it "
            f"({'unknown row count' if n is None else str(n) + ' rows'}); rotating would break it. "
            "Anyone with repo access knows this value. Marked with "
            f"{LEGACY_MARKERS[key]}=1. To rotate: export your Langfuse data, then "
            "./uninstall.sh --volumes && ./install.sh."
        )

    for k, v in new_env.items():
        lines = _set_env(lines, k, v)
    # Legacy markers are meaningless once the value is strong.
    for key, marker in LEGACY_MARKERS.items():
        if marker in values and marker not in new_env and (key in new_env or not is_insecure(values.get(key, ""))):
            lines = _del_env(lines, marker)
    # These now live in niyan.yaml only (single source for CLI + API).
    lines = [
        l for l in lines
        if l.strip().split("=", 1)[0].strip() not in {"NIYAN_ADMIN_PASSWORD", "NIYAN_JWT_SECRET", "LITELLM_MASTER_KEY"}
    ]

    text = yaml_path.read_bytes().decode("utf-8") if yaml_path.exists() else ""  # keep CRLF
    for key, gen in (("password", new_admin_password), ("jwt_secret", lambda: _hex(32))):
        cur, _ = _yaml_section_value(text, "admin_auth", key)
        if cur and not is_insecure(cur):
            report["kept"].append(f"admin_auth.{key}")
        else:
            text = _yaml_set(text, "admin_auth", key, gen())
            report["generated"].append(f"admin_auth.{key}")
    old_keys = _yaml_api_keys(text)
    keys = [k for k in old_keys if not is_insecure(k)]
    if keys:
        report["kept"].append("proxy.api_keys")
    else:
        keys = [f"sk-niyan-{_hex(24)}"]
        report["generated"].append("proxy.api_keys")
    if keys != old_keys:
        text = _yaml_set_api_keys(text, keys)

    _write_env(env_path, lines)
    write_private(yaml_path, text)
    return report


def check_secrets(env: Dict[str, str]) -> List[str]:
    """Names of secrets in a Compose env that are empty or shipped defaults."""
    names = ["NIYAN_ADMIN_PASSWORD", "NIYAN_JWT_SECRET", "LITELLM_MASTER_KEY", *ENV_SECRETS]
    out = []
    for n in names:
        if not is_insecure(env.get(n, "")):
            continue
        marker = LEGACY_MARKERS.get(n)
        if marker and env.get(marker) == "1" and env.get(n):
            continue  # documented legacy value kept for data compatibility
        out.append(n)
    return out
