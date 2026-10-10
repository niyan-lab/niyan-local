from __future__ import annotations

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from app.auth import require_admin
from app.container import provide_orchestrator
from app.schemas.models import ServiceStatus, ServicesResponse
from app.services import health_checker
from app.services.orchestrator import Orchestrator

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict:
    agg = await health_checker.health_aggregate()
    return {"status": "ok", **agg}


@router.get("/services", response_model=ServicesResponse)
async def services(
    _: str = Depends(require_admin),
    orchestrator: Orchestrator = Depends(provide_orchestrator),
) -> ServicesResponse:
    return ServicesResponse(services=await run_in_threadpool(orchestrator.list_services))


@router.post("/services/{name}/restart", response_model=ServiceStatus)
async def restart(
    name: str,
    _: str = Depends(require_admin),
    orchestrator: Orchestrator = Depends(provide_orchestrator),
) -> ServiceStatus:
    return await run_in_threadpool(orchestrator.restart_service, name)
