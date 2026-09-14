from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import require_admin
from app.schemas.models import ObservabilityUpdate
from app.services import config_manager, health_checker
from app.settings import settings

router = APIRouter(prefix="/api/observability", tags=["observability"])


def _status_payload(cfg) -> dict:
    obs = cfg.observability
    pub = (obs.public_key or "").strip()
    return {
        "enabled": obs.enabled,
        "provider": obs.provider,
        "host": obs.host,
        "ui_url": "http://localhost:3100",
        "keys_configured": bool(pub and (obs.secret_key or "").strip()),
        "public_key_last4": pub[-4:] if len(pub) >= 4 else ("" if not pub else pub),
        "secret_key_set": bool((obs.secret_key or "").strip()),
    }


@router.get("/status")
async def observability_status(_: str = Depends(require_admin)) -> dict:
    cfg = config_manager.load_config()
    reachable = await health_checker.probe(f"{settings.langfuse_url.rstrip('/')}")
    return {**_status_payload(cfg), "reachable": reachable}


@router.put("")
async def update_observability(
    body: ObservabilityUpdate, _: str = Depends(require_admin)
) -> dict:
    cfg = config_manager.load_config()
    obs = cfg.observability
    if body.enabled is not None:
        obs.enabled = body.enabled
    if body.public_key is not None and body.public_key.strip():
        obs.public_key = body.public_key.strip()
    if body.secret_key is not None and body.secret_key.strip():
        obs.secret_key = body.secret_key.strip()
    if body.host is not None and body.host.strip():
        obs.host = body.host.strip()
    config_manager.save_config(cfg)
    reachable = await health_checker.probe(f"{settings.langfuse_url.rstrip('/')}")
    return {
        **_status_payload(cfg),
        "reachable": reachable,
        "note": "Keys saved to niyan.yaml; the gateway reads them live for new traces.",
    }
