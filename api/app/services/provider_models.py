"""List the models an API key can actually reach, per provider.

The curated cards in `data/proprietary_models.json` describe the models Niyan
ships routing for. This module asks the provider what the configured key is
entitled to, so the Proprietary page can show models the account has beyond the
curated set (and flag curated ones the key cannot reach).
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import httpx

_TIMEOUT = 10.0

# Non-chat endpoints share the /models listing; they are not routable through
# the chat gateway, so drop them rather than showing dead entries.
_OPENAI_SKIP_PREFIXES = (
    "dall-e",
    "whisper",
    "tts-",
    "text-embedding",
    "omni-moderation",
    "text-moderation",
    "babbage",
    "davinci",
)


async def _openai(api_key: str) -> List[str]:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        r.raise_for_status()
        ids = [item.get("id", "") for item in r.json().get("data", [])]
    return [i for i in ids if i and not i.startswith(_OPENAI_SKIP_PREFIXES)]


async def _gemini(api_key: str) -> List[str]:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key},
        )
        r.raise_for_status()
        out: List[str] = []
        for item in r.json().get("models", []):
            methods = item.get("supportedGenerationMethods") or []
            if methods and "generateContent" not in methods:
                continue
            # API returns fully-qualified names like "models/gemini-2.5-flash".
            name = (item.get("name") or "").split("/")[-1]
            if name:
                out.append(name)
    return out


async def _anthropic(api_key: str) -> List[str]:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.get(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        )
        r.raise_for_status()
        return [item.get("id", "") for item in r.json().get("data", []) if item.get("id")]


_FETCHERS = {
    "openai": _openai,
    "gemini": _gemini,
    "anthropic": _anthropic,
}


async def list_models(provider: str, api_key: str) -> Tuple[Optional[List[str]], str]:
    """Return (model_ids, detail). `None` means the lookup could not be made."""
    fetch = _FETCHERS.get((provider or "").strip().lower())
    if fetch is None:
        return None, f"unsupported provider: {provider}"
    if not (api_key or "").strip():
        return None, "No API key configured"
    try:
        return sorted(await fetch(api_key.strip())), ""
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        if code in (401, 403):
            return None, "API key rejected by provider"
        return None, f"Provider returned HTTP {code}"
    except Exception as exc:
        return None, f"Could not reach provider ({exc.__class__.__name__})"
