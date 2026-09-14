from __future__ import annotations

import time
from typing import List

import docker
import httpx
from docker.errors import DockerException

from app.schemas.models import ServiceStatus
from app.settings import settings

# Mac / Windows Docker Desktop: Ollama is a host process, not a Compose service.
_HOST_OLLAMA_MARKERS = ("host.docker.internal", "localhost", "127.0.0.1", "[::1]")


CORE_SERVICES = [
    "gateway",
    "litellm",
    "redis",
    "niyan-api",
    "ollama",
    "langfuse-web",
    "postgres",
    "guardrails",
    "nemo-guardrails",
    "admin-ui",
    "qdrant",
    "loadtest",
]


def uses_host_ollama_url(host: str) -> bool:
    """True when OLLAMA_HOST points at the machine running Docker Desktop."""
    h = (host or "").strip().lower()
    return bool(h) and any(token in h for token in _HOST_OLLAMA_MARKERS)


def probe_ollama(host: str, timeout: float = 3.0) -> bool:
    try:
        r = httpx.get(f"{host.rstrip('/')}/api/tags", timeout=timeout)
        return r.status_code < 500
    except Exception:
        return False


def host_ollama_status(host: str, reachable: bool) -> ServiceStatus:
    return ServiceStatus(
        name="ollama",
        status="host" if reachable else "unreachable",
        healthy=reachable,
        detail=host or "host process",
    )


def list_services() -> List[ServiceStatus]:
    try:
        client = docker.from_env()
    except DockerException as exc:
        return [
            ServiceStatus(
                name="docker",
                status="unavailable",
                healthy=False,
                detail=str(exc),
            )
        ]

    found = {s: None for s in CORE_SERVICES}
    for container in client.containers.list(all=True):
        name = container.name
        # compose names like niyan-gateway-1
        for svc in CORE_SERVICES:
            if f"-{svc}-" in f"-{name}-" or name.endswith(f"-{svc}-1") or name == svc:
                found[svc] = container
                break

    results: List[ServiceStatus] = []
    for svc, container in found.items():
        # Host Ollama has no compose container; a leftover stopped one is not the backend.
        if svc == "ollama" and uses_host_ollama_url(settings.ollama_host):
            results.append(
                host_ollama_status(settings.ollama_host, probe_ollama(settings.ollama_host))
            )
            continue
        if container is None:
            results.append(
                ServiceStatus(name=svc, status="not_created", healthy=False, detail="not running")
            )
            continue
        state = container.status
        healthy = state == "running"
        # healthcheck if present
        try:
            insp = container.attrs.get("State", {})
            health = insp.get("Health", {}).get("Status")
            if health:
                healthy = health == "healthy"
                state = health
        except Exception:
            pass
        results.append(
            ServiceStatus(
                name=svc,
                status=state,
                healthy=healthy,
                detail=container.short_id,
            )
        )
    return results


def restart_service(name: str) -> ServiceStatus:
    client = docker.from_env()
    matches = [
        c
        for c in client.containers.list(all=True)
        if f"-{name}-" in f"-{c.name}-" or c.name.endswith(f"-{name}-1") or c.name == name
    ]
    if not matches:
        return ServiceStatus(name=name, status="not_found", healthy=False, detail="container not found")
    container = matches[0]
    container.restart()
    return ServiceStatus(name=name, status="restarted", healthy=True, detail=container.short_id)


def _find_container(name: str):
    client = docker.from_env()
    matches = [
        c
        for c in client.containers.list(all=True)
        if f"-{name}-" in f"-{c.name}-" or c.name.endswith(f"-{name}-1") or c.name == name
    ]
    if not matches:
        return None
    return matches[0]


def start_loadtest(
    *,
    run_id: str,
    job_path: str,
    out_dir: str,
    users: int,
    spawn_rate: float,
    duration_sec: int,
    host: str,
) -> None:
    """Start Locust headless inside the loadtest container (detached)."""
    container = _find_container("loadtest")
    if container is None or container.status != "running":
        raise RuntimeError(
            "loadtest container is not running — rebuild with `niyan up --build`"
        )
    # Kill any leftover Locust from a previous interrupted run
    try:
        container.exec_run(["pkill", "-f", "locust"], demux=True)
        time.sleep(0.5)
    except Exception:
        pass

    duration = f"{int(duration_sec)}s"
    cmd = [
        "locust",
        "-f",
        "/app/locustfile.py",
        "--headless",
        "-u",
        str(int(users)),
        "-r",
        str(spawn_rate),
        "-t",
        duration,
        "--host",
        host,
        "--html",
        f"{out_dir}/report.html",
        "--csv",
        f"{out_dir}/run",
        "--only-summary",
    ]
    # Detached exec so API returns immediately; env points locustfile at this job.
    client = docker.from_env()
    exec_id = client.api.exec_create(
        container.id,
        cmd,
        environment={
            "LOADTEST_JOB_PATH": job_path,
            "LOADTEST_OUT_DIR": out_dir,
            "LOADTEST_RUN_ID": run_id,
        },
        workdir="/app",
    )
    client.api.exec_start(exec_id, detach=True)


def stop_loadtest() -> None:
    container = _find_container("loadtest")
    if container is None:
        raise RuntimeError("loadtest container not found")
    exit_code, _ = container.exec_run(["pkill", "-f", "locust"], demux=True)
    # pkill returns 1 when nothing matched — treat as ok if not running
    if exit_code not in (0, 1):
        raise RuntimeError(f"pkill failed with exit {exit_code}")


def loadtest_is_running() -> bool:
    container = _find_container("loadtest")
    if container is None or container.status != "running":
        return False
    exit_code, output = container.exec_run(["pgrep", "-f", "locust"], demux=True)
    if exit_code != 0:
        return False
    stdout = output[0] if isinstance(output, tuple) else output
    text = (stdout or b"").decode("utf-8", errors="replace").strip()
    return bool(text)
