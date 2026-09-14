"""Load testing API — Locust runs against gateway presets or a custom endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from app.auth import require_admin
from app.schemas.loadtest import LoadTestCreate, LoadTestRun
from app.services import loadtest_runner

router = APIRouter(prefix="/api/loadtests", tags=["loadtests"])


@router.get("/presets")
async def list_presets(_: str = Depends(require_admin)) -> dict:
    return {
        "presets": loadtest_runner.presets(),
        "limits": {
            "max_users": loadtest_runner.MAX_USERS,
            "max_duration_sec": loadtest_runner.MAX_DURATION_SEC,
            "min_duration_sec": loadtest_runner.MIN_DURATION_SEC,
            "one_active_run": True,
        },
        "note": (
            "Gateway presets hit the Niyan OpenAI-compatible gateway. "
            "Custom endpoint supports one URL with optional internal-URL override."
        ),
    }


@router.get("")
async def list_loadtests(_: str = Depends(require_admin)) -> dict:
    runs = loadtest_runner.list_runs()
    active = loadtest_runner.find_active_run_id()
    return {
        "runs": [r.model_dump(mode="json") for r in runs],
        "active_run_id": active,
    }


@router.post("", response_model=LoadTestRun)
async def create_loadtest(
    body: LoadTestCreate, _: str = Depends(require_admin)
) -> LoadTestRun:
    return loadtest_runner.create_and_start(body)


@router.get("/{run_id}", response_model=LoadTestRun)
async def get_loadtest(run_id: str, _: str = Depends(require_admin)) -> LoadTestRun:
    run = loadtest_runner.get_run(run_id)
    if not run:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.post("/{run_id}/stop", response_model=LoadTestRun)
async def stop_loadtest(run_id: str, _: str = Depends(require_admin)) -> LoadTestRun:
    return loadtest_runner.stop_run(run_id)


@router.get("/{run_id}/download")
async def download_loadtest(
    run_id: str,
    format: str = Query("json", description="json | html | csv"),
    inline: bool = Query(False, description="If true, open HTML inline instead of attachment"),
    _: str = Depends(require_admin),
):
    path = loadtest_runner.download_path(run_id, format)
    media = {
        "json": "application/json",
        "html": "text/html",
        "csv": "text/csv",
    }.get(format.lower(), "application/octet-stream")
    filename = f"niyan-loadtest-{run_id}.{format.lower()}"
    if inline and format.lower() == "html":
        return FileResponse(
            path,
            media_type=media,
            filename=filename,
            content_disposition_type="inline",
        )
    return FileResponse(path, media_type=media, filename=filename)


@router.get("/{run_id}/report")
async def view_loadtest_report(run_id: str, _: str = Depends(require_admin)):
    """Serve Locust HTML report for in-browser viewing."""
    path = loadtest_runner.download_path(run_id, "html")
    return FileResponse(
        path,
        media_type="text/html",
        filename=f"niyan-loadtest-{run_id}.html",
        content_disposition_type="inline",
    )
