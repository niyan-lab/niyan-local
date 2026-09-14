from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import require_admin
from app.schemas.models import ServiceStatus, ServicesResponse
from app.services import docker_manager, health_checker

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict:
    agg = await health_checker.health_aggregate()
    return {"status": "ok", **agg}


@router.get("/services", response_model=ServicesResponse)
async def services(_: str = Depends(require_admin)) -> ServicesResponse:
    return ServicesResponse(services=docker_manager.list_services())


@router.post("/services/{name}/restart", response_model=ServiceStatus)
async def restart(name: str, _: str = Depends(require_admin)) -> ServiceStatus:
    return docker_manager.restart_service(name)
