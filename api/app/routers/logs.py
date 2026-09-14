from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.auth import require_admin

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/{service}")
async def stream_logs(service: str, _: str = Depends(require_admin)):
    import docker
    from docker.errors import DockerException

    try:
        client = docker.from_env()
    except DockerException as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    matches = [
        c
        for c in client.containers.list(all=True)
        if f"-{service}-" in f"-{c.name}-" or c.name.endswith(f"-{service}-1") or c.name == service
    ]
    if not matches:
        raise HTTPException(status_code=404, detail=f"service {service} not found")
    container = matches[0]

    async def gen():
        # Emit recent logs then keep polling briefly
        logs = container.logs(tail=100).decode("utf-8", errors="replace")
        for line in logs.splitlines():
            yield {"data": line}
            await asyncio.sleep(0)

    return EventSourceResponse(gen())
