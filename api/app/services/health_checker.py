from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, List, Optional, Set

import httpx

from app.settings import settings


async def ollama_tags() -> Set[str]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{settings.ollama_host.rstrip('/')}/api/tags")
            r.raise_for_status()
            models = r.json().get("models", [])
            names: Set[str] = set()
            for m in models:
                name = m.get("name") or m.get("model")
                if name:
                    names.add(name)
                    names.add(name.split(":")[0])
            return names
    except Exception:
        return set()


async def ollama_models() -> Optional[List[Dict[str, Any]]]:
    """Full /api/tags payload — size, quantization, and parameter count per tag.

    Returns None (rather than []) when Ollama is unreachable so callers can tell
    "no models pulled" apart from "cannot ask".
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{settings.ollama_host.rstrip('/')}/api/tags")
            r.raise_for_status()
            out: List[Dict[str, Any]] = []
            for m in r.json().get("models", []) or []:
                name = m.get("name") or m.get("model")
                if not name:
                    continue
                details = m.get("details") or {}
                out.append(
                    {
                        "id": name,
                        "size_bytes": m.get("size"),
                        "modified_at": m.get("modified_at") or "",
                        "parameter_size": details.get("parameter_size") or "",
                        "quantization": details.get("quantization_level") or "",
                        "family": details.get("family") or "",
                    }
                )
            return out
    except Exception:
        return None


async def pull_model(name: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=None) as client:
        r = await client.post(
            f"{settings.ollama_host.rstrip('/')}/api/pull",
            json={"name": name, "stream": False},
        )
        r.raise_for_status()
        return r.json() if r.content else {"status": "ok", "name": name}


async def pull_model_stream(name: str) -> AsyncIterator[Dict[str, Any]]:
    """Yield Ollama pull progress chunks (status, digest, total, completed)."""
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            f"{settings.ollama_host.rstrip('/')}/api/pull",
            json={"name": name, "stream": True},
        ) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


async def delete_model(name: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.request(
            "DELETE",
            f"{settings.ollama_host.rstrip('/')}/api/delete",
            json={"name": name},
        )
        if r.status_code >= 400:
            return {"ok": False, "detail": r.text}
        return {"ok": True, "name": name}


async def ollama_ps() -> Set[str]:
    """Names of models currently loaded in Ollama memory (GET /api/ps)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{settings.ollama_host.rstrip('/')}/api/ps")
            r.raise_for_status()
            models = r.json().get("models", [])
            names: Set[str] = set()
            for m in models:
                name = m.get("name") or m.get("model")
                if name:
                    names.add(name)
                    names.add(name.split(":")[0])
            return names
    except Exception:
        return set()


async def _set_keep_alive(name: str, keep_alive: Any) -> Dict[str, Any]:
    """Load (keep_alive>0/-1) or unload (keep_alive=0) a model in Ollama memory.

    Chat models use /api/generate; embedding models don't support it, so we
    fall back to /api/embeddings so load/eject works for both.
    """
    base = settings.ollama_host.rstrip("/")
    async with httpx.AsyncClient(timeout=120.0) as client:
        gen = await client.post(
            f"{base}/api/generate",
            json={"model": name, "keep_alive": keep_alive},
        )
        if gen.status_code < 400:
            return {"ok": True, "name": name}
        # Embedding models: /api/generate is unsupported — use embeddings endpoint.
        emb = await client.post(
            f"{base}/api/embeddings",
            json={"model": name, "prompt": "", "keep_alive": keep_alive},
        )
        if emb.status_code < 400:
            return {"ok": True, "name": name}
        return {"ok": False, "detail": gen.text or emb.text}


async def load_model(name: str) -> Dict[str, Any]:
    """Load a model into memory and keep it resident until ejected."""
    return await _set_keep_alive(name, -1)


async def eject_model(name: str) -> Dict[str, Any]:
    """Unload a model from memory (keep on disk) via keep_alive=0."""
    return await _set_keep_alive(name, 0)


async def probe(url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(url)
            return r.status_code < 500
    except Exception:
        return False


async def health_aggregate() -> Dict[str, Any]:
    checks = {
        "gateway": await probe(f"{settings.gateway_url}/health"),
        "ollama": await probe(f"{settings.ollama_host.rstrip('/')}/api/tags"),
        "langfuse": await probe(f"{settings.langfuse_url.rstrip('/')}"),
    }
    provider = (settings.guardrails_provider or "llm_guard").lower().replace("-", "_")
    if provider == "nemo":
        checks["guard_nemo"] = await probe(f"{settings.guard_nemo_url}/health")
    else:
        checks["guard_llm"] = await probe(f"{settings.guard_llm_url}/health")
    checks["qdrant"] = await probe(f"{settings.qdrant_url.rstrip('/')}/readyz")
    return {"ok": checks.get("gateway", False), "checks": checks}
