"""Provider API key management."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import require_admin
from app.schemas.models import ProviderPublic, ProvidersPublic, ProvidersUpdate
from app.services import config_manager
from app.services.litellm_gen import apply_provider_changes

router = APIRouter(prefix="/api/providers", tags=["providers"])


def _public_cred(enabled: bool, api_key: str) -> ProviderPublic:
    key = (api_key or "").strip()
    return ProviderPublic(
        enabled=enabled,
        configured=bool(key),
        api_key_last4=key[-4:] if len(key) >= 4 else ("" if not key else key),
    )


def _public(cfg) -> ProvidersPublic:
    return ProvidersPublic(
        openai=_public_cred(cfg.providers.openai.enabled, cfg.providers.openai.api_key),
        gemini=_public_cred(cfg.providers.gemini.enabled, cfg.providers.gemini.api_key),
        anthropic=_public_cred(cfg.providers.anthropic.enabled, cfg.providers.anthropic.api_key),
    )


def _apply_update(cred, body) -> None:
    if body.enabled is not None:
        cred.enabled = body.enabled
    if body.api_key is not None and body.api_key.strip():
        cred.api_key = body.api_key.strip()


@router.get("", response_model=ProvidersPublic)
async def get_providers(_: str = Depends(require_admin)) -> ProvidersPublic:
    cfg = config_manager.load_config()
    return _public(cfg)


@router.put("")
async def put_providers(body: ProvidersUpdate, _: str = Depends(require_admin)) -> dict:
    cfg = config_manager.load_config()
    if body.openai is not None:
        _apply_update(cfg.providers.openai, body.openai)
    if body.gemini is not None:
        _apply_update(cfg.providers.gemini, body.gemini)
    if body.anthropic is not None:
        _apply_update(cfg.providers.anthropic, body.anthropic)
    config_manager.save_config(cfg)
    apply = apply_provider_changes(cfg)
    return {
        "providers": _public(cfg).model_dump(),
        "note": "LiteLLM config regenerated; litellm restarted",
        **apply,
    }
