from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import run_in_threadpool

from app.auth import require_admin
from app.container import provide_orchestrator
from app.services.orchestrator import Orchestrator, ServiceNotFoundError

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/{service}")
async def stream_logs(
    service: str,
    _: str = Depends(require_admin),
    orchestrator: Orchestrator = Depends(provide_orchestrator),
):
    try:
        lines = await run_in_threadpool(orchestrator.stream_logs, service, 100)
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # backend unavailable / not implemented
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    async def gen():
        for line in lines:
            yield {"data": line}
            await asyncio.sleep(0)

    return EventSourceResponse(gen())
