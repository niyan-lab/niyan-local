"""Composition root: ConfigStore + Docker orchestrator (Compose / VM only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Request

from app.platform import resolve_platform
from app.services.config_store import ConfigStore, build_config_store
from app.services.orchestrator import DockerOrchestrator, Orchestrator
from app.settings import settings


@dataclass
class Container:
    platform: str
    config_store: ConfigStore
    orchestrator: Orchestrator


def build_container(
    platform: Optional[str] = None,
    *,
    config_store: Optional[ConfigStore] = None,
    orchestrator: Optional[Orchestrator] = None,
) -> Container:
    # platform arg kept for test overrides; production always resolves to vm.
    plat = platform or resolve_platform()
    if plat != "vm":
        plat = "vm"
    if config_store is None:
        config_store = build_config_store(settings)
    if orchestrator is None:
        orchestrator = DockerOrchestrator()
    return Container(platform=plat, config_store=config_store, orchestrator=orchestrator)


_container: Optional[Container] = None


def get_container() -> Container:
    global _container
    if _container is None:
        _container = build_container()
    return _container


def set_container(container: Container) -> None:
    global _container
    _container = container


def reset_container() -> None:
    global _container
    _container = None


def provide_orchestrator(request: Request) -> Orchestrator:
    container = getattr(request.app.state, "container", None) or get_container()
    return container.orchestrator
