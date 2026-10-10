"""
Orchestrator for niyan-api on Compose / VM (Docker socket).

This repo (`niyan-local`) is local-deployment only — no Kubernetes client.
Cluster orchestration lives in niyan-complete.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.schemas.models import ServiceStatus

logger = logging.getLogger(__name__)

docker_manager = None
try:  # pragma: no cover
    from app.services import docker_manager as _docker_manager  # type: ignore

    docker_manager = _docker_manager
except Exception:  # pragma: no cover
    docker_manager = None


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


class ServiceNotFoundError(RuntimeError):
    """Raised when a service/container cannot be located for an operation (log stream)."""


class Orchestrator:
    def list_services(self) -> List[ServiceStatus]:  # pragma: no cover (interface)
        raise NotImplementedError

    def restart_service(self, name: str) -> ServiceStatus:  # pragma: no cover
        raise NotImplementedError

    def start_loadtest(
        self,
        *,
        run_id: str,
        job_path: str,
        out_dir: str,
        users: int,
        spawn_rate: float,
        duration_sec: int,
        host: str,
        job_body: Optional[Dict[str, Any]] = None,
    ) -> None:  # pragma: no cover
        raise NotImplementedError

    def stop_loadtest(self, run_id: Optional[str] = None) -> None:  # pragma: no cover
        raise NotImplementedError

    def loadtest_is_running(self, run_id: Optional[str] = None) -> bool:  # pragma: no cover
        raise NotImplementedError

    def stream_logs(self, service: str, tail: int = 100) -> List[str]:  # pragma: no cover
        raise NotImplementedError


class DockerOrchestrator(Orchestrator):
    def list_services(self) -> List[ServiceStatus]:
        if not docker_manager:
            raise RuntimeError("docker orchestrator requested but docker_manager unavailable")
        return docker_manager.list_services()

    def restart_service(self, name: str) -> ServiceStatus:
        if not docker_manager:
            raise RuntimeError("docker orchestrator requested but docker_manager unavailable")
        return docker_manager.restart_service(name)

    def start_loadtest(
        self,
        *,
        run_id: str,
        job_path: str,
        out_dir: str,
        users: int,
        spawn_rate: float,
        duration_sec: int,
        host: str,
        job_body: Optional[Dict[str, Any]] = None,
    ) -> None:
        # job_body unused: Compose shares a bind-mounted filesystem with the loadtest
        # container (job.json written by loadtest_runner).
        if not docker_manager:
            raise RuntimeError("docker orchestrator requested but docker_manager unavailable")
        return docker_manager.start_loadtest(
            run_id=run_id,
            job_path=job_path,
            out_dir=out_dir,
            users=users,
            spawn_rate=spawn_rate,
            duration_sec=duration_sec,
            host=host,
        )

    def stop_loadtest(self, run_id: Optional[str] = None) -> None:
        if not docker_manager:
            raise RuntimeError("docker orchestrator requested but docker_manager unavailable")
        return docker_manager.stop_loadtest()

    def loadtest_is_running(self, run_id: Optional[str] = None) -> bool:
        if not docker_manager:
            raise RuntimeError("docker orchestrator requested but docker_manager unavailable")
        return docker_manager.loadtest_is_running()

    def stream_logs(self, service: str, tail: int = 100) -> List[str]:
        import docker
        from docker.errors import DockerException

        try:
            client = docker.from_env()
        except DockerException as exc:  # backend unavailable
            raise RuntimeError(str(exc)) from exc
        matches = [
            c
            for c in client.containers.list(all=True)
            if f"-{service}-" in f"-{c.name}-"
            or c.name.endswith(f"-{service}-1")
            or c.name == service
        ]
        if not matches:
            raise ServiceNotFoundError(f"service {service} not found")
        raw = matches[0].logs(tail=tail).decode("utf-8", errors="replace")
        return raw.splitlines()
