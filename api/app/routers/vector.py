"""Vector store + embeddings control-plane routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_admin
from app.schemas.models import (
    CollectionCreate,
    EmbeddingsUpdate,
    SearchRequest,
    UpsertRequest,
    VectorUpdate,
)
from app.services import config_manager
from app.services.vector_store import get_store
from app.settings import settings

router = APIRouter(tags=["vector"])


@router.get("/api/embeddings/config")
async def get_embeddings(_: str = Depends(require_admin)) -> dict:
    cfg = config_manager.load_config()
    return cfg.embeddings.model_dump(mode="json")


@router.put("/api/embeddings/config")
async def put_embeddings(body: EmbeddingsUpdate, _: str = Depends(require_admin)) -> dict:
    cfg = config_manager.load_config()
    if body.enabled is not None:
        cfg.embeddings.enabled = body.enabled
    if body.model is not None:
        cfg.embeddings.model = body.model
    config_manager.save_config(cfg)
    return {
        "ok": True,
        "embeddings": cfg.embeddings.model_dump(mode="json"),
        "note": "Pull the model with `niyan embeddings pull` (or `niyan model pull <name>`)",
    }


@router.get("/api/vector/config")
async def get_vector_config(_: str = Depends(require_admin)) -> dict:
    cfg = config_manager.load_config()
    return {
        **cfg.vector.model_dump(mode="json"),
        "runtime": {
            "enabled_env": settings.vector_enabled,
            "provider_env": settings.vector_provider,
            "qdrant_url": settings.qdrant_url,
        },
    }


@router.put("/api/vector/config")
async def put_vector_config(body: VectorUpdate, _: str = Depends(require_admin)) -> dict:
    cfg = config_manager.load_config()
    if body.enabled is not None:
        cfg.vector.enabled = body.enabled
    if body.provider is not None:
        cfg.vector.provider = body.provider
    if body.qdrant_port is not None:
        cfg.vector.qdrant.port = body.qdrant_port
    if body.pgvector_database is not None:
        cfg.vector.pgvector.database = body.pgvector_database
    config_manager.save_config(cfg)
    return {
        "ok": True,
        "vector": cfg.vector.model_dump(mode="json"),
        "note": "Run `niyan vector provider …` or `niyan up` to apply compose profile changes",
    }


@router.get("/api/vector/health")
async def vector_health(_: str = Depends(require_admin)) -> dict:
    cfg = config_manager.load_config()
    if not cfg.vector.enabled and not settings.vector_enabled:
        return {"ok": False, "enabled": False, "detail": "vector store disabled in config"}
    store = get_store()
    result = await store.health()
    result["enabled"] = True
    result["config_provider"] = cfg.vector.provider.value if hasattr(cfg.vector.provider, "value") else cfg.vector.provider
    return result


@router.get("/api/vector/collections")
async def list_collections(_: str = Depends(require_admin)) -> dict:
    _require_enabled()
    try:
        cols = await get_store().list_collections()
        return {"collections": cols}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/api/vector/collections")
async def create_collection(body: CollectionCreate, _: str = Depends(require_admin)) -> dict:
    _require_enabled()
    try:
        return await get_store().create_collection(body.name, body.size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.delete("/api/vector/collections/{name}")
async def delete_collection(name: str, _: str = Depends(require_admin)) -> dict:
    _require_enabled()
    try:
        return await get_store().delete_collection(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/api/vector/upsert")
async def upsert(body: UpsertRequest, _: str = Depends(require_admin)) -> dict:
    _require_enabled()
    if not body.points:
        raise HTTPException(status_code=400, detail="points required")
    try:
        points = [p.model_dump() for p in body.points]
        return await get_store().upsert(body.collection, points)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/api/vector/search")
async def search(body: SearchRequest, _: str = Depends(require_admin)) -> dict:
    _require_enabled()
    try:
        hits = await get_store().search(body.collection, body.vector, body.limit)
        return {"hits": hits}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _require_enabled() -> None:
    cfg = config_manager.load_config()
    if not cfg.vector.enabled and not settings.vector_enabled:
        raise HTTPException(
            status_code=400,
            detail="Vector store disabled. Set vector.enabled=true and recreate the stack.",
        )
