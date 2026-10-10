"""Enterprise AI Policy — domain → local/proprietary model routing."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_admin
from app.schemas.models import (
    DEFAULT_LOCAL_MODEL,
    DEFAULT_PROPRIETARY_MODEL,
    DomainPolicy,
    EnterprisePolicyUpdate,
    ModelProvider,
    PolicyMode,
)
from app.services import config_manager

router = APIRouter(prefix="/api/enterprise-policy", tags=["enterprise-policy"])


def _catalog(cfg) -> dict:
    local = [
        {"id": m.id, "provider": m.provider.value, "enabled": m.enabled}
        for m in cfg.models
        if m.provider == ModelProvider.ollama
    ]
    proprietary = [
        {
            "id": m.id,
            "provider": m.provider.value,
            "enabled": m.enabled,
            "ready": cfg.provider_ready(m.provider),
        }
        for m in cfg.models
        if m.provider in {ModelProvider.openai, ModelProvider.gemini, ModelProvider.anthropic}
    ]
    return {"local": local, "proprietary": proprietary}


def _payload(cfg) -> dict:
    return {
        "policy": cfg.enterprise_policy.model_dump(mode="json"),
        "catalog": _catalog(cfg),
        "defaults": {
            "local_model": DEFAULT_LOCAL_MODEL,
            "proprietary_model": DEFAULT_PROPRIETARY_MODEL,
        },
        "note": (
            "Clients send model as a domain id (e.g. finance). "
            "The deployment bar chooses local_model vs proprietary_model (default Gemini)."
        ),
    }


@router.get("")
async def get_enterprise_policy(_: str = Depends(require_admin)) -> dict:
    cfg = config_manager.load_config()
    return _payload(cfg)


@router.put("")
async def put_enterprise_policy(
    body: EnterprisePolicyUpdate, _: str = Depends(require_admin)
) -> dict:
    cfg = config_manager.load_config()
    if body.enabled is not None:
        cfg.enterprise_policy.enabled = body.enabled
    if body.mode is not None:
        if body.mode == PolicyMode.auto:
            raise HTTPException(
                status_code=400,
                detail="Auto mode is not implemented yet — use manual",
            )
        cfg.enterprise_policy.mode = body.mode
    if body.domains is not None:
        seen = set()
        cleaned: list[DomainPolicy] = []
        for d in body.domains:
            domain_id = (d.id or "").strip().lower()
            if not domain_id:
                raise HTTPException(status_code=400, detail="domain id is required")
            if domain_id in seen:
                raise HTTPException(status_code=400, detail=f"duplicate domain id: {domain_id}")
            seen.add(domain_id)
            if not (d.local_model or "").strip():
                raise HTTPException(
                    status_code=400, detail=f"domain '{domain_id}' needs local_model"
                )
            if not (d.proprietary_model or "").strip():
                raise HTTPException(
                    status_code=400, detail=f"domain '{domain_id}' needs proprietary_model"
                )
            cleaned.append(
                DomainPolicy(
                    id=domain_id,
                    enabled=d.enabled,
                    deployment=d.deployment,
                    local_model=d.local_model.strip(),
                    proprietary_model=d.proprietary_model.strip(),
                )
            )
        cfg.enterprise_policy.domains = cleaned
    config_manager.save_config(cfg)
    return {
        **_payload(cfg),
        "ok": True,
        "saved": "Policy saved; gateway remaps domains on the next request.",
    }
