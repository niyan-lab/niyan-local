from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.container import build_container, set_container
from app.services.config_store import ConfigReadOnlyError
from app.settings import settings
from app.routers import (
    auth,
    dashboard,
    enterprise_policy,
    gateway,
    guardrails,
    inference,
    loadtests,
    logs,
    models,
    observability,
    providers,
    services,
    vector,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.assert_secure()
    container = build_container()
    set_container(container)
    app.state.container = container
    yield


app = FastAPI(
    title="Niyan Control Plane",
    version="0.1.0",
    description="Orchestrates Niyan stack config, models, gateway, guardrails, vectors, and observability.",
    lifespan=lifespan,
)

_origins = settings.cors_origins_list()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=bool(_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ConfigReadOnlyError)
async def _config_readonly_handler(_: Request, exc: ConfigReadOnlyError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


app.include_router(auth.router)
app.include_router(services.router)
app.include_router(dashboard.router)
app.include_router(models.router)
app.include_router(inference.router)
app.include_router(providers.router)
app.include_router(gateway.router)
app.include_router(guardrails.router)
app.include_router(observability.router)
app.include_router(enterprise_policy.router)
app.include_router(loadtests.router)
app.include_router(vector.router)
app.include_router(logs.router)


@app.get("/")
async def root() -> dict:
    return {"name": "niyan-api", "docs": "/docs"}
