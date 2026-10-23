"""Docker Compose lifecycle helpers for Niyan."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List, Optional

from niyan.config import GuardrailsProvider, NiyanConfig, Profile, VectorProvider, uses_host_ollama
from niyan.doctor import detect_profile


def find_repo_root(start: Optional[Path] = None) -> Path:
    # Conda-style: NIYAN_ROOT from shell init wins so `niyan` works from any cwd.
    for key in ("NIYAN_ROOT", "NIYAN_HOME"):
        env = os.environ.get(key)
        if env:
            root = Path(env).expanduser().resolve()
            if (root / "deploy" / "docker-compose.yml").exists() or (
                root / "configs" / "niyan.example.yaml"
            ).exists():
                return root

    cur = (start or Path.cwd()).resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / "deploy" / "docker-compose.yml").exists():
            return candidate
        if (candidate / "configs" / "niyan.example.yaml").exists():
            return candidate
    # Fall back to package-relative: cli/niyan -> repo root is parents[2]
    here = Path(__file__).resolve()
    return here.parents[2]


def local_builder() -> str:
    """
    Builder to use for local stack builds.

    Multi-arch release builds need a `docker-container` builder, and creating one
    with `--use` makes it the global default. That driver keeps its own image
    store, so every local build gets exported to an OCI tarball and streamed into
    the daemon — minutes per service even when every layer is cached. The current
    context always names a `docker` driver builder that writes straight to the
    daemon, so pin to that instead of whatever is globally selected.
    """
    try:
        proc = subprocess.run(
            ["docker", "context", "show"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return proc.stdout.strip() or "default"
    except Exception:
        return "default"


def compose_files(repo_root: Path, profile: Profile) -> List[Path]:
    files = [repo_root / "deploy" / "docker-compose.yml"]
    if uses_host_ollama(profile):
        host = repo_root / "deploy" / "docker-compose.host-ollama.yml"
        mac = repo_root / "deploy" / "docker-compose.mac.yml"
        if host.exists():
            files.append(host)
        elif mac.exists():
            files.append(mac)
    elif profile == Profile.linux_gpu:
        gpu = repo_root / "deploy" / "docker-compose.linux-gpu.yml"
        if gpu.exists():
            files.append(gpu)
    return files


def compose_cmd(repo_root: Path, profile: Profile, config: NiyanConfig) -> List[str]:
    cmd = ["docker", "compose", "--project-name", "niyan"]
    for f in compose_files(repo_root, profile):
        cmd.extend(["-f", str(f)])

    profiles: List[str] = []
    if not uses_host_ollama(profile):
        profiles.append("ollama")
    if config.observability.enabled:
        profiles.append("obs")
    if config.guardrails.enabled:
        if config.guardrails.provider == GuardrailsProvider.llm_guard:
            profiles.append("guard-llm")
        else:
            profiles.append("guard-nemo")
    if config.admin.enabled:
        profiles.append("admin")
    if config.vector.enabled:
        if config.vector.provider == VectorProvider.qdrant:
            profiles.append("vector-qdrant")
        else:
            profiles.append("vector-pg")

    for p in profiles:
        cmd.extend(["--profile", p])
    return cmd


def guardrails_url(config: NiyanConfig) -> str:
    if not config.guardrails.enabled:
        return ""
    if config.guardrails.provider == GuardrailsProvider.llm_guard:
        return "http://guardrails:8088"
    return "http://nemo-guardrails:8089"


def resolve_langfuse_host(host: str, profile: Profile) -> str:
    """Map user-facing Langfuse URLs to addresses reachable from Docker containers."""
    h = (host or "").strip().rstrip("/")
    if not h:
        return "http://langfuse-web:3000"

    # Bundled Niyan Langfuse (host port 3100 → container langfuse-web:3000)
    if any(
        x in h
        for x in (
            "localhost:3100",
            "127.0.0.1:3100",
            "langfuse:3100",
            "langfuse-web:3100",
        )
    ):
        return "http://langfuse-web:3000"

    # Common misconfig: wrong service name / port inside compose network
    if h in {"http://langfuse:3000", "http://langfuse"}:
        return "http://langfuse-web:3000"

    # Existing Langfuse already running on the host :3000
    if any(x in h for x in ("localhost:3000", "127.0.0.1:3000")):
        if uses_host_ollama(profile):
            return "http://host.docker.internal:3000"
        return "http://172.17.0.1:3000"

    return h


def build_env(repo_root: Path, profile: Profile, config: NiyanConfig) -> dict:
    import json

    from niyan.pricing import model_providers_map, pricing_json

    env = os.environ.copy()
    # Both of these cost minutes on a fully cached `up --build` and neither is
    # useful for a local stack. setdefault so an explicit export still wins.
    env.setdefault("BUILDX_BUILDER", local_builder())
    env.setdefault("BUILDX_NO_DEFAULT_ATTESTATIONS", "1")
    # Docker Desktop on Windows accepts native paths; prefer resolved absolute path.
    env["NIYAN_ROOT"] = str(repo_root.resolve())
    env["COMPOSE_PROJECT_NAME"] = "niyan"
    env["LITELLM_MASTER_KEY"] = config.proxy.api_keys[0] if config.proxy.api_keys else ""
    env["GUARDRAILS_PROVIDER"] = config.guardrails.provider.value
    env["GUARDRAILS_URL"] = guardrails_url(config)
    env["GUARDRAILS_ENABLED"] = "true" if config.guardrails.enabled else "false"
    env["GUARDRAILS_ON_FAILURE"] = config.guardrails.on_failure.value
    env["LLM_GUARD_SCANNERS"] = ",".join(config.guardrails.llm_guard.scanners)
    env["LLM_GUARD_OUTPUT_SCANNERS"] = ",".join(config.guardrails.llm_guard.output_scanners)
    env["NIYAN_ADMIN_USERNAME"] = config.admin_auth.username
    env["NIYAN_ADMIN_PASSWORD"] = config.admin_auth.password
    env["NIYAN_JWT_SECRET"] = config.admin_auth.jwt_secret
    env["PROXY_PORT"] = str(config.proxy.port)
    env["API_PORT"] = str(config.api.port)
    env["ADMIN_PORT"] = str(config.admin.port)
    env.setdefault("LANGFUSE_PORT", "3100")

    env["VECTOR_ENABLED"] = "true" if config.vector.enabled else "false"
    env["VECTOR_PROVIDER"] = config.vector.provider.value
    env["QDRANT_PORT"] = str(config.vector.qdrant.port)
    env["QDRANT_URL"] = "http://qdrant:6333"
    env["POSTGRES_VECTOR_DB"] = config.vector.pgvector.database or "niyan_vectors"
    env["EMBEDDINGS_ENABLED"] = "true" if config.embeddings.enabled else "false"
    env["EMBEDDINGS_MODEL"] = config.embeddings.model or "nomic-embed-text"

    env["OPENAI_API_KEY"] = config.providers.openai.api_key or ""
    env["GEMINI_API_KEY"] = config.providers.gemini.api_key or ""
    env["ANTHROPIC_API_KEY"] = config.providers.anthropic.api_key or ""
    env["NIYAN_PRICING_JSON"] = json.dumps(pricing_json(config))
    env["NIYAN_MODEL_PROVIDERS"] = json.dumps(model_providers_map(config))

    # Propagate Langfuse keys from niyan.yaml into Compose (otherwise containers see empty keys)
    if config.observability.enabled and config.observability.provider == "langfuse":
        env["LANGFUSE_PUBLIC_KEY"] = config.observability.public_key or ""
        env["LANGFUSE_SECRET_KEY"] = config.observability.secret_key or ""
        env["LANGFUSE_HOST"] = resolve_langfuse_host(config.observability.host, profile)
    else:
        env.setdefault("LANGFUSE_PUBLIC_KEY", "")
        env.setdefault("LANGFUSE_SECRET_KEY", "")
        env.setdefault("LANGFUSE_HOST", "http://langfuse-web:3000")

    if uses_host_ollama(profile):
        env["OLLAMA_HOST"] = "http://host.docker.internal:11434"
    else:
        env["OLLAMA_HOST"] = config.ollama.host or "http://ollama:11434"

    env_file = repo_root / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            key = k.strip()
            # Do not let empty .env Langfuse keys overwrite yaml-provided keys
            if key in {"LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"} and not v.strip():
                continue
            if key == "LANGFUSE_HOST" and not v.strip():
                continue
            env.setdefault(key, v.strip())

    pg_user = env.get("POSTGRES_USER", "niyan")
    pg_pass = env.get("POSTGRES_PASSWORD", "")
    vector_db = config.vector.pgvector.database or "niyan_vectors"
    env["PGVECTOR_DSN"] = f"postgresql://{pg_user}:{pg_pass}@postgres:5432/{vector_db}"
    return env


def ensure_litellm_config(repo_root: Path, config: NiyanConfig) -> Path:
    from niyan.litellm_gen import generate_litellm_config

    return generate_litellm_config(config, repo_root)


# Compose interpolates every ${VAR:?} guard even for `down`/`logs`/`exec`.
GUARDED_VARS = (
    "POSTGRES_PASSWORD",
    "LANGFUSE_NEXTAUTH_SECRET",
    "LANGFUSE_SALT",
    "LANGFUSE_ENCRYPTION_KEY",
    "LITELLM_MASTER_KEY",
    "NIYAN_ADMIN_PASSWORD",
    "NIYAN_JWT_SECRET",
)
PLACEHOLDER = "__niyan_unused__"


def placeholder_env(env: dict) -> dict:
    """Fill empty guarded vars with a dummy so non-starting commands work."""
    out = dict(env)
    for k in GUARDED_VARS:
        if not (out.get(k) or "").strip():
            out[k] = PLACEHOLDER
    return out


def run_compose(
    repo_root: Path,
    config: NiyanConfig,
    args: List[str],
    check: bool = True,
    placeholders: bool = False,
) -> subprocess.CompletedProcess:
    profile = detect_profile(config.profile)
    ensure_litellm_config(repo_root, config)
    cmd = compose_cmd(repo_root, profile, config) + args
    env = build_env(repo_root, profile, config)
    if placeholders:
        env = placeholder_env(env)
    return subprocess.run(cmd, cwd=str(repo_root), env=env, check=check)


class InsecureSecretsError(RuntimeError):
    pass


def assert_secure_env(env: dict) -> None:
    """Refuse to start with empty / shipped-default secrets unless NIYAN_ALLOW_INSECURE_DEFAULTS=1."""
    from niyan.secrets_init import check_secrets
    from niyan.secrets_policy import insecure_allowed

    bad = check_secrets(env)
    if bad and not insecure_allowed(env):
        raise InsecureSecretsError(
            "Refusing to start: empty or default secrets: " + ", ".join(bad)
            + ". Run `niyan secrets init` (or ./install.sh). For throwaway dev only, set "
            "NIYAN_ALLOW_INSECURE_DEFAULTS=1."
        )


def stack_up(repo_root: Path, config: NiyanConfig, *, build: bool = False) -> None:
    ensure_litellm_config(repo_root, config)
    assert_secure_env(build_env(repo_root, detect_profile(config.profile), config))
    args = ["up", "-d", "--remove-orphans"]
    if build:
        args.insert(2, "--build")
    run_compose(repo_root, config, args)


def recreate_litellm(repo_root: Path, config: NiyanConfig) -> None:
    """Regenerate LiteLLM config and force-recreate the litellm (+ gateway) containers."""
    ensure_litellm_config(repo_root, config)
    run_compose(
        repo_root,
        config,
        ["up", "-d", "--force-recreate", "--no-deps", "litellm", "gateway"],
        check=False,
    )


def stack_down(repo_root: Path, config: NiyanConfig, volumes: bool = False) -> None:
    args = ["down", "--remove-orphans"]
    if volumes:
        args.append("--volumes")
    run_compose(repo_root, config, args, check=False, placeholders=True)


def stack_ps(repo_root: Path, config: NiyanConfig) -> str:
    proc = run_compose(repo_root, config, ["ps"], check=False)
    return (proc.stdout or "") if hasattr(proc, "stdout") else ""


def stack_logs(repo_root: Path, config: NiyanConfig, service: Optional[str], follow: bool) -> None:
    args = ["logs", "--tail", "200"]
    if follow:
        args.append("-f")
    if service:
        args.append(service)
    # Don't capture — stream to terminal
    profile = detect_profile(config.profile)
    cmd = compose_cmd(repo_root, profile, config) + args
    env = placeholder_env(build_env(repo_root, profile, config))
    subprocess.run(cmd, cwd=str(repo_root), env=env)
