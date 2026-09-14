"""Live host / stack resource metrics (CPU, memory, optional GPU)."""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Seed psutil so subsequent cpu_percent(None) calls are non-zero.
_psutil_ready = False


def collect_resources() -> Dict[str, Any]:
    cpu = _cpu()
    memory = _memory()
    gpu = _gpu()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cpu": cpu,
        "memory": memory,
        "gpu": gpu,
    }


def _cpu() -> Dict[str, Any]:
    try:
        import psutil

        global _psutil_ready
        if not _psutil_ready:
            psutil.cpu_percent(interval=None)
            _psutil_ready = True
            # Brief sample so the first dashboard paint isn't stuck at 0.
            percent = float(psutil.cpu_percent(interval=0.15))
        else:
            percent = float(psutil.cpu_percent(interval=None))
        return {
            "percent": round(percent, 1),
            "count": int(psutil.cpu_count() or 0),
            "available": True,
        }
    except Exception as exc:
        return {"percent": None, "count": None, "available": False, "detail": str(exc)}


def _memory() -> Dict[str, Any]:
    try:
        import psutil

        vm = psutil.virtual_memory()
        return {
            "percent": round(float(vm.percent), 1),
            "used_bytes": int(vm.used),
            "total_bytes": int(vm.total),
            "available": True,
        }
    except Exception as exc:
        return {
            "percent": None,
            "used_bytes": None,
            "total_bytes": None,
            "available": False,
            "detail": str(exc),
        }


def _gpu() -> Dict[str, Any]:
    devices = _gpu_nvidia_smi() or _gpu_via_docker_exec()
    if not devices:
        return {
            "available": False,
            "devices": [],
            "detail": "No NVIDIA GPU detected (nvidia-smi unavailable)",
        }
    return {"available": True, "devices": devices, "detail": ""}


def _parse_nvidia_smi(out: str) -> List[Dict[str, Any]]:
    devices: List[Dict[str, Any]] = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        try:
            index = int(parts[0])
            name = parts[1]
            util = float(parts[2])
            mem_used_mib = float(parts[3])
            mem_total_mib = float(parts[4])
        except (TypeError, ValueError):
            continue
        used_b = int(mem_used_mib * 1024 * 1024)
        total_b = int(mem_total_mib * 1024 * 1024)
        mem_pct = round((used_b / total_b) * 100, 1) if total_b else 0.0
        devices.append(
            {
                "index": index,
                "name": name,
                "utilization_percent": round(util, 1),
                "memory_used_bytes": used_b,
                "memory_total_bytes": total_b,
                "memory_percent": mem_pct,
            }
        )
    return devices


_NVIDIA_QUERY = [
    "nvidia-smi",
    "--query-gpu=index,name,utilization.gpu,memory.used,memory.total",
    "--format=csv,noheader,nounits",
]


def _gpu_nvidia_smi() -> Optional[List[Dict[str, Any]]]:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        proc = subprocess.run(_NVIDIA_QUERY, capture_output=True, text=True, timeout=3)
        if proc.returncode != 0:
            return None
        devices = _parse_nvidia_smi(proc.stdout or "")
        return devices or None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _match_service(container_name: str, service: str) -> bool:
    name = container_name or ""
    return (
        f"-{service}-" in f"-{name}-"
        or name.endswith(f"-{service}-1")
        or name == service
    )


def _gpu_via_docker_exec() -> Optional[List[Dict[str, Any]]]:
    """Try nvidia-smi inside a running Niyan container (e.g. ollama with GPU)."""
    try:
        import docker
        from docker.errors import DockerException
    except ImportError:
        return None
    try:
        client = docker.from_env()
    except DockerException:
        return None

    # Prefer ollama — that's where local model inference (and GPU) usually lives.
    candidates = ["ollama", "gateway", "litellm", "niyan-api"]
    containers = client.containers.list()
    for prefer in candidates:
        for container in containers:
            if not _match_service(container.name or "", prefer):
                continue
            try:
                exit_code, output = container.exec_run(_NVIDIA_QUERY, demux=True)
                if exit_code != 0:
                    continue
                stdout = output[0] if isinstance(output, tuple) else output
                text = (stdout or b"").decode("utf-8", errors="replace")
                devices = _parse_nvidia_smi(text)
                if devices:
                    return devices
            except Exception:
                continue
    return None
