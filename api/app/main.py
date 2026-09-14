from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

app = FastAPI(
    title="Niyan Control Plane",
    version="0.1.0",
    description="Orchestrates Niyan stack config, models, gateway, guardrails, vectors, and observability.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
