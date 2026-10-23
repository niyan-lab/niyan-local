from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import require_admin
from app.schemas.models import NiyanConfig, ProxyConfig
from app.services import config_manager
from app.services.config_secrets import mask_secrets

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/config", response_model=NiyanConfig)
async def get_config(_: str = Depends(require_admin)) -> NiyanConfig:
    return mask_secrets(config_manager.load_config())


@router.put("/config", response_model=NiyanConfig)
async def put_config(body: NiyanConfig, _: str = Depends(require_admin)) -> NiyanConfig:
    # Masked/empty/default secret values in the body keep the stored ones.
    return mask_secrets(config_manager.save_config(body))


@router.get("/gateway/config")
async def gateway_config(_: str = Depends(require_admin)) -> dict:
    cfg = config_manager.load_config()
    return {
        "port": cfg.proxy.port,
        "api_keys": cfg.proxy.api_keys,
        "models": [m.model_dump() for m in cfg.models if m.enabled],
    }


@router.put("/gateway/config")
async def put_gateway_config(body: ProxyConfig, _: str = Depends(require_admin)) -> dict:
    from fastapi import HTTPException

    from app.secrets_policy import is_insecure

    if not body.api_keys or any(is_insecure(k) for k in body.api_keys):
        raise HTTPException(status_code=400, detail="api_keys must be non-empty and not a default/placeholder")
    cfg = config_manager.load_config()
    cfg.proxy = body
    saved = config_manager.save_config(cfg)
    return {"ok": True, "proxy": {"port": saved.proxy.port, "api_keys_count": len(saved.proxy.api_keys)}}
