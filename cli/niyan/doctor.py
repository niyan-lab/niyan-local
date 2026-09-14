"""Hardware / dependency diagnostics and profile resolution."""

from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from niyan.config import NiyanConfig, Profile, uses_host_ollama


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


@dataclass
class DoctorReport:
    resolved_profile: Profile
    checks: List[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks if c.name in {"docker", "compose"})


def _run(cmd: List[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        out = (proc.stdout or proc.stderr or "").strip()
        return proc.returncode, out
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def detect_profile(config_profile: Profile = Profile.auto) -> Profile:
    if config_profile != Profile.auto:
        return config_profile
    system = platform.system().lower()
    if system == "darwin":
        return Profile.mac
    if system == "windows":
        return Profile.windows
    code, _ = _run(["nvidia-smi"])
    if code == 0:
        return Profile.linux_gpu
    return Profile.linux_cpu


def run_doctor(config: Optional[NiyanConfig] = None, repo_root: Optional[Path] = None) -> DoctorReport:
    profile = detect_profile(config.profile if config else Profile.auto)
    checks: List[CheckResult] = []

    docker = shutil.which("docker")
    checks.append(
        CheckResult(
            name="docker",
            ok=docker is not None,
            detail=docker or "docker not found on PATH",
        )
    )

    if docker:
        code, out = _run(["docker", "info"])
        checks.append(
            CheckResult(
                name="docker_daemon",
                ok=code == 0,
                detail="Docker daemon reachable" if code == 0 else out[:200],
            )
        )
        code, out = _run(["docker", "compose", "version"])
        checks.append(
            CheckResult(
                name="compose",
                ok=code == 0,
                detail=out.splitlines()[0] if code == 0 else "docker compose unavailable",
            )
        )
    else:
        checks.append(CheckResult(name="compose", ok=False, detail="requires docker"))

    ollama = shutil.which("ollama")
    if uses_host_ollama(profile):
        host_label = "Windows" if profile == Profile.windows else "Mac"
        checks.append(
            CheckResult(
                name="ollama_host",
                ok=ollama is not None,
                detail=(
                    f"host Ollama found at {ollama}"
                    if ollama
                    else (
                        f"Install Ollama on the {host_label} host "
                        "(https://ollama.com). Niyan uses host Ollama via "
                        "host.docker.internal — not Compose Ollama — on this profile."
                    )
                ),
            )
        )
        if ollama:
            code, out = _run(["ollama", "list"])
            checks.append(
                CheckResult(
                    name="ollama_running",
                    ok=code == 0,
                    detail="ollama responding" if code == 0 else "start Ollama app or `ollama serve`",
                )
            )
    else:
        checks.append(
            CheckResult(
                name="ollama",
                ok=True,
                detail="Ollama will run in Docker Compose on Linux profiles",
            )
        )

    if config and config.guardrails.enabled and config.guardrails.on_failure.value == "allow":
        checks.append(
            CheckResult(
                name="guardrails_on_failure",
                ok=True,
                detail="on_failure=allow (local DX). Failures will not block requests.",
            )
        )

    if repo_root and not (repo_root / "deploy" / "docker-compose.yml").exists():
        checks.append(
            CheckResult(
                name="repo",
                ok=False,
                detail=f"deploy/docker-compose.yml missing under {repo_root}",
            )
        )

    return DoctorReport(resolved_profile=profile, checks=checks)
