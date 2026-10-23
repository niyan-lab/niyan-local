from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import require_admin
from app.schemas.models import NiyanConfig, ProxyConfig
from app.services import config_manager
from app.services.config_secrets import MASK, merge_incoming, mask_secrets

KEYS_READ_ONLY = (
    "Gateway API keys are read-only here: the gateway only enforces keys it was started with. "
    "Rotate with `niyan secrets rotate gateway-key`, then run `niyan up`."
)


def _keys_changed(incoming: Optional[List[str]], current: List[str]) -> bool:
    if incoming is None:
        return False
    if incoming and all(k == MASK for k in incoming) and len(incoming) == len(current):
        return False  # masked echo of the stored keys
    return list(incoming) != list(current)


class GatewayUpdate(BaseModel):
    port: int
    api_keys: Optional[List[str]] = None  # read-only; only accepted unchanged

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/config", response_model=NiyanConfig)
async def get_config(_: str = Depends(require_admin)) -> NiyanConfig:
    return mask_secrets(config_manager.load_config())


@router.put("/config", response_model=NiyanConfig)
async def put_config(body: NiyanConfig, _: str = Depends(require_admin)) -> NiyanConfig:
    # Masked/empty/default secret values in the body keep the stored ones.
    current = config_manager.load_config()
    if merge_incoming(body, current).proxy.api_keys != list(current.proxy.api_keys):
        raise HTTPException(status_code=409, detail=KEYS_READ_ONLY)
    return mask_secrets(config_manager.save_config(body))


@router.get("/gateway/config")
async def gateway_config(_: str = Depends(require_admin)) -> dict:
    cfg = config_manager.load_config()
    return {
        "port": cfg.proxy.port,
        "api_keys": cfg.proxy.api_keys,
        "api_keys_read_only": True,
        "api_keys_hint": KEYS_READ_ONLY,
        "models": [m.model_dump() for m in cfg.models if m.enabled],
    }


@router.put("/gateway/config")
async def put_gateway_config(body: GatewayUpdate, _: str = Depends(require_admin)) -> dict:
    cfg = config_manager.load_config()
    if _keys_changed(body.api_keys, cfg.proxy.api_keys):
        raise HTTPException(status_code=409, detail=KEYS_READ_ONLY)
    cfg.proxy = ProxyConfig(**{**cfg.proxy.model_dump(), "port": body.port})
    saved = config_manager.save_config(cfg)
    return {"ok": True, "proxy": {"port": saved.proxy.port, "api_keys_count": len(saved.proxy.api_keys)}}
