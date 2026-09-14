from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.auth import require_admin
from app.schemas.models import (
    ModelEntry,
    ModelInfo,
    ModelProvider,
    ModelsResponse,
    ModelUpdate,
    PullRequest,
)
from app.services import catalog, config_manager, health_checker, model_registry
from app.services.litellm_gen import apply_provider_changes

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("", response_model=ModelsResponse)
async def list_models(_: str = Depends(require_admin)) -> ModelsResponse:
    cfg = config_manager.load_config()
    installed = await health_checker.ollama_tags()
    loaded = await health_checker.ollama_ps()
    models = []
    for m in cfg.models:
        ready = cfg.provider_ready(m.provider)
        is_local = m.provider == ModelProvider.ollama
        models.append(
            ModelInfo(
                id=m.id,
                family=m.family,
                provider=m.provider.value,
                deployment=m.deployment,
                enabled=m.enabled,
                default=m.default,
                installed=(
                    m.id in installed or m.id.split(":")[0] in installed if is_local else ready
                ),
                loaded=(is_local and (m.id in loaded or m.id.split(":")[0] in loaded)),
                provider_ready=ready,
                can_pull=is_local,
            )
        )
    if cfg.embeddings.enabled and cfg.embeddings.model:
        emb = cfg.embeddings.model
        if not any(m.id == emb for m in models):
            models.append(
                ModelInfo(
                    id=emb,
                    family="embedding",
                    provider="ollama",
                    deployment="local",
                    enabled=True,
                    default=False,
                    installed=emb in installed or emb.split(":")[0] in installed,
                    loaded=emb in loaded or emb.split(":")[0] in loaded,
                    provider_ready=True,
                    can_pull=True,
                )
            )
    return ModelsResponse(models=models)


@router.put("/{model_id}")
async def update_model(model_id: str, body: ModelUpdate, _: str = Depends(require_admin)) -> dict:
    cfg = config_manager.load_config()
    target = next((m for m in cfg.models if m.id == model_id), None)
    if target is None and body.provider is not None:
        target = _register_model(cfg, model_id, body)
    if target is None:
        raise HTTPException(status_code=404, detail=f"model not found: {model_id}")
    if body.enabled is not None:
        if body.enabled and not cfg.provider_ready(target.provider):
            raise HTTPException(
                status_code=400,
                detail=f"Provider {target.provider.value} is not configured — set API key under Providers",
            )
        target.enabled = body.enabled
    if body.default is not None and body.default:
        for m in cfg.models:
            m.default = m.id == model_id
        target.enabled = True
    # Ensure at least one enabled
    if not any(m.enabled for m in cfg.models):
        raise HTTPException(status_code=400, detail="At least one model must remain enabled")
    config_manager.save_config(cfg)
    apply = apply_provider_changes(cfg)
    return {"ok": True, "model": target.model_dump(mode="json"), **apply}


def _register_model(cfg, model_id: str, body: ModelUpdate) -> ModelEntry:
    """Add a model the portal knows about but niyan.yaml does not carry yet."""
    card = catalog.proprietary_card(model_id) or catalog.on_prem_card(model_id)
    entry = ModelEntry(
        id=model_id,
        provider=body.provider,
        family=body.family or (card.family if card else body.provider.value),
        enabled=False,
        default=False,
    )
    cfg.models.append(entry)
    return entry


@router.post("/pull")
async def pull_model(body: PullRequest, _: str = Depends(require_admin)) -> dict:
    cfg = config_manager.load_config()
    entry = next((m for m in cfg.models if m.id == body.name), None)
    name = body.name
    proprietary = False
    if entry and entry.provider != ModelProvider.ollama:
        proprietary = True
    else:
        lower = name.lower()
        if lower.startswith(("gemini", "gpt-", "o1", "o3", "chatgpt", "claude")):
            proprietary = True
        elif entry and entry.family in {"gemini", "gpt", "openai", "claude", "anthropic"}:
            proprietary = True
    if proprietary:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{name} is a proprietary cloud model — enable it on the Models page "
                "(Providers → API key, then toggle Enable). Pull is only for Ollama."
            ),
        )
    try:
        result = await health_checker.pull_model(body.name)
        return {"ok": True, "name": body.name, "result": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/pull/stream")
async def pull_model_stream(body: PullRequest, _: str = Depends(require_admin)):
    cfg = config_manager.load_config()
    entry = next((m for m in cfg.models if m.id == body.name), None)
    if entry and entry.provider != ModelProvider.ollama:
        raise HTTPException(
            status_code=400,
            detail=f"{body.name} is proprietary — enable it under Models (no pull)",
        )
    if model_registry.ensure_local_model(cfg, body.name):
        config_manager.save_config(cfg)

    async def gen():
        yield {"event": "start", "data": json.dumps({"name": body.name})}
        # Ollama reports each blob separately; keep a running total so the UI
        # bar reflects the whole download instead of resetting per layer.
        layers: dict[str, tuple[int, int]] = {}
        last_sent = 0.0
        last_percent: float | None = None
        last_status = ""
        try:
            async for chunk in health_checker.pull_model_stream(body.name):
                status = str(chunk.get("status") or "")
                digest = str(chunk.get("digest") or "")
                total = chunk.get("total")
                completed = chunk.get("completed")
                if digest and isinstance(total, (int, float)) and total:
                    layers[digest] = (int(completed or 0), int(total))
                overall_completed = sum(c for c, _t in layers.values())
                overall_total = sum(t for _c, t in layers.values())
                if overall_total:
                    percent: float | None = round(overall_completed / overall_total * 100, 1)
                elif isinstance(total, (int, float)) and total and isinstance(completed, (int, float)):
                    percent = round(completed / total * 100, 1)
                    overall_completed, overall_total = int(completed), int(total)
                else:
                    percent = None

                now = time.monotonic()
                status_changed = status != last_status
                percent_moved = (
                    percent is not None
                    and (last_percent is None or abs(percent - last_percent) >= 0.3)
                )
                if not status_changed and not percent_moved and now - last_sent < 0.25:
                    continue

                last_sent = now
                last_percent = percent
                last_status = status
                yield {
                    "event": "progress",
                    "data": json.dumps(
                        {
                            "status": status,
                            "percent": percent,
                            "completed": overall_completed or completed,
                            "total": overall_total or total,
                        }
                    ),
                }
            yield {"event": "done", "data": json.dumps({"ok": True, "name": body.name})}
            try:
                apply_provider_changes(cfg)
            except Exception:
                pass
        except Exception as exc:
            yield {"event": "error", "data": json.dumps({"ok": False, "detail": str(exc)})}

    return EventSourceResponse(
        gen(),
        ping=15,
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/{name}/load")
async def load_model(name: str, _: str = Depends(require_admin)) -> dict:
    """Load a model into Ollama memory (keeps it resident until ejected)."""
    result = await health_checker.load_model(name)
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("detail") or "load failed")
    return result


@router.post("/{name}/eject")
async def eject_model(name: str, _: str = Depends(require_admin)) -> dict:
    """Unload a model from Ollama memory (keeps weights on disk)."""
    result = await health_checker.eject_model(name)
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("detail") or "eject failed")
    return result


@router.delete("/{name}")
async def delete_model(name: str, _: str = Depends(require_admin)) -> dict:
    """Delete a model's weights from disk (Ollama)."""
    result = await health_checker.delete_model(name)
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("detail") or "delete failed")

    # Auto-adopted models are re-added on the next listing if the weights come
    # back. Leaving the entry behind would keep an unroutable model in LiteLLM.
    cfg = config_manager.load_config()
    entry = model_registry.find_entry(cfg, name)
    seeded = {m.id for m in config_manager.CURATED_MODELS}
    if entry is not None and entry.id not in seeded and not entry.default:
        cfg.models = [m for m in cfg.models if m.id != entry.id]
        if any(m.enabled for m in cfg.models):
            config_manager.save_config(cfg)
            apply_provider_changes(cfg)
            result["removed_from_config"] = entry.id
    return result
