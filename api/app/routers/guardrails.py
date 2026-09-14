from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import require_admin
from app.schemas.models import GuardrailsUpdate
from app.services import config_manager

router = APIRouter(prefix="/api/guardrails", tags=["guardrails"])


@router.get("/config")
async def get_guardrails(_: str = Depends(require_admin)) -> dict:
    cfg = config_manager.load_config()
    return cfg.guardrails.model_dump(mode="json")


@router.put("/config")
async def put_guardrails(body: GuardrailsUpdate, _: str = Depends(require_admin)) -> dict:
    cfg = config_manager.load_config()
    if body.enabled is not None:
        cfg.guardrails.enabled = body.enabled
    if body.provider is not None:
        cfg.guardrails.provider = body.provider
    if body.on_failure is not None:
        cfg.guardrails.on_failure = body.on_failure
    if body.scanners is not None:
        cfg.guardrails.llm_guard.scanners = body.scanners
    if body.output_scanners is not None:
        cfg.guardrails.llm_guard.output_scanners = body.output_scanners
    config_manager.save_config(cfg)
    return {
        "ok": True,
        "guardrails": cfg.guardrails.model_dump(mode="json"),
        "note": "Run `niyan up` (or recreate compose profiles) to apply provider switch",
    }
