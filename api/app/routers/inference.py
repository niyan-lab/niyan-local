"""Inference pages: on-prem (Ollama) and proprietary (cloud provider) models."""

from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends, Query

from app.auth import require_admin
from app.schemas.catalog import (
    CatalogResponse,
    LibraryResponse,
    OnPremModel,
    OnPremResponse,
    ProprietaryResponse,
    ProviderModel,
    ProviderSection,
)
from app.schemas.models import ModelProvider
from app.services import catalog, config_manager, health_checker, model_registry, ollama_library
from app.services import provider_models as provider_models_api

router = APIRouter(prefix="/api/inference", tags=["inference"])

PROVIDER_META = [
    ("openai", "OpenAI", "https://platform.openai.com/api-keys"),
    ("gemini", "Google Gemini", "https://aistudio.google.com/app/apikey"),
    ("anthropic", "Anthropic", "https://console.anthropic.com/settings/keys"),
]


@router.get("/on-prem", response_model=OnPremResponse)
async def on_prem(_: str = Depends(require_admin)) -> OnPremResponse:
    """Self-hosted models: config entries merged with Ollama's actual inventory."""
    cfg = config_manager.load_config()
    discovered = await health_checker.ollama_models()
    reachable = discovered is not None
    inventory: List[Dict[str, object]] = discovered or []

    adopted = model_registry.adopt_discovered(cfg, inventory)
    if adopted:
        model_registry.persist_adoptions(cfg, adopted)

    by_id: Dict[str, Dict[str, object]] = {
        model_registry.normalize(str(item.get("id"))): item for item in inventory
    }
    loaded = await health_checker.ollama_ps()

    models: List[OnPremModel] = []
    seen = set()
    for entry in cfg.models:
        if entry.provider != ModelProvider.ollama:
            continue
        key = model_registry.normalize(entry.id)
        seen.add(key)
        detail = by_id.get(key) or {}
        models.append(
            _on_prem_model(
                model_id=entry.id,
                family=entry.family,
                enabled=entry.enabled,
                default=entry.default,
                detail=detail,
                installed=bool(detail),
                loaded=_is_loaded(entry.id, loaded),
            )
        )

    # The embeddings model lives outside `models:` in niyan.yaml.
    emb = model_registry.normalize(cfg.embeddings.model or "")
    if cfg.embeddings.enabled and emb and emb not in seen:
        detail = by_id.get(emb) or {}
        models.append(
            _on_prem_model(
                model_id=emb,
                family="embedding",
                enabled=True,
                default=False,
                detail=detail,
                installed=bool(detail),
                loaded=_is_loaded(emb, loaded),
            )
        )

    models.sort(key=lambda m: (not m.installed, m.card is None, m.id))
    return OnPremResponse(models=models, adopted=adopted, ollama_reachable=reachable)


def _is_loaded(model_id: str, loaded: set) -> bool:
    name = model_registry.normalize(model_id)
    return name in loaded or name.split(":")[0] in loaded


def _on_prem_model(
    *,
    model_id: str,
    family: str,
    enabled: bool,
    default: bool,
    detail: Dict[str, object],
    installed: bool,
    loaded: bool,
) -> OnPremModel:
    card = catalog.on_prem_card(model_id)
    size = detail.get("size_bytes")
    return OnPremModel(
        id=model_id,
        family=family or (card.family if card else ""),
        enabled=enabled,
        installed=installed,
        loaded=loaded,
        default=default,
        managed=True,
        size_bytes=int(size) if isinstance(size, (int, float)) else None,
        parameter_size=str(detail.get("parameter_size") or (card.parameters if card else "")),
        quantization=str(detail.get("quantization") or ""),
        modified_at=str(detail.get("modified_at") or ""),
        card=card,
    )


@router.get("/on-prem/catalog", response_model=CatalogResponse)
async def on_prem_catalog(_: str = Depends(require_admin)) -> CatalogResponse:
    """Every curated card, installed or not — the 'add a model' browser."""
    return CatalogResponse(cards=catalog.on_prem_cards())


@router.get("/library", response_model=LibraryResponse)
async def library(
    q: str = Query("", description="Search the public Ollama library"),
    _: str = Depends(require_admin),
) -> LibraryResponse:
    return await ollama_library.search(q)


@router.get("/proprietary", response_model=ProprietaryResponse)
async def proprietary(
    refresh: bool = Query(False, description="Ask each provider which models the key can reach"),
    _: str = Depends(require_admin),
) -> ProprietaryResponse:
    cfg = config_manager.load_config()
    sections: List[ProviderSection] = []

    for name, title, docs_url in PROVIDER_META:
        cred = getattr(cfg.providers, name)
        api_key = (cred.api_key or "").strip()
        configured = bool(api_key)

        live_ids: List[str] = []
        live_ok = False
        detail = ""
        if refresh and configured:
            fetched, detail = await provider_models_api.list_models(name, api_key)
            if fetched is not None:
                live_ids = fetched
                live_ok = True

        provider_enum = ModelProvider(name)
        entries = {m.id: m for m in cfg.models if m.provider == provider_enum}
        live_set = set(live_ids)

        models: List[ProviderModel] = []
        seen = set()
        for card in catalog.proprietary_cards_for(name):
            entry = entries.get(card.id)
            seen.add(card.id)
            models.append(
                ProviderModel(
                    id=card.id,
                    name=card.name,
                    provider=name,
                    family=card.family,
                    enabled=bool(entry and entry.enabled),
                    default=bool(entry and entry.default),
                    configured=configured,
                    in_config=entry is not None,
                    available_live=(card.id in live_set) if live_ok else None,
                    card=card,
                )
            )

        # Models the key can reach that Niyan has no card for.
        for model_id in live_ids:
            if model_id in seen:
                continue
            entry = entries.get(model_id)
            models.append(
                ProviderModel(
                    id=model_id,
                    name=model_id,
                    provider=name,
                    family=name,
                    enabled=bool(entry and entry.enabled),
                    default=bool(entry and entry.default),
                    configured=configured,
                    in_config=entry is not None,
                    available_live=True,
                    card=None,
                )
            )

        sections.append(
            ProviderSection(
                name=name,
                title=title,
                docs_url=docs_url,
                enabled=cred.enabled,
                configured=configured,
                api_key_last4=api_key[-4:] if len(api_key) >= 4 else api_key,
                models=models,
                live_refreshed=live_ok,
                detail=detail,
            )
        )

    return ProprietaryResponse(providers=sections)
