from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import require_admin
from app.schemas.models import NiyanConfig, ProxyConfig
from app.services import config_manager

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/config", response_model=NiyanConfig)
async def get_config(_: str = Depends(require_admin)) -> NiyanConfig:
    return config_manager.load_config()


@router.put("/config", response_model=NiyanConfig)
async def put_config(body: NiyanConfig, _: str = Depends(require_admin)) -> NiyanConfig:
    return config_manager.save_config(body)


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
    cfg = config_manager.load_config()
    cfg.proxy = body
    config_manager.save_config(cfg)
    return {"ok": True, "proxy": body.model_dump()}
