"""Search the public Ollama library so any model can be pulled, not just curated ones.

ollama.com has no documented search API, so this scrapes the search page and
degrades to a curated-catalog match when the host is offline — which is the
normal case for air-gapped installs.
"""

from __future__ import annotations

import re
from typing import List

import httpx

from app.schemas.catalog import LibraryModel, LibraryResponse
from app.services import catalog

_SEARCH_URL = "https://ollama.com/search"
_LIBRARY_HREF = re.compile(r'href="/library/([a-zA-Z0-9._\-]+)"')


def _curated_matches(query: str) -> List[LibraryModel]:
    q = (query or "").strip().lower()
    out: List[LibraryModel] = []
    for card in catalog.on_prem_cards():
        haystack = f"{card.id} {card.name} {card.family} {card.publisher} {card.modality}".lower()
        if q and q not in haystack:
            continue
        out.append(
            LibraryModel(
                id=card.id,
                name=card.name,
                description=card.summary,
                tags=[card.modality, card.parameters],
                curated=True,
            )
        )
    return out


async def search(query: str, limit: int = 40) -> LibraryResponse:
    curated = _curated_matches(query)
    q = (query or "").strip()
    if not q:
        return LibraryResponse(results=curated[:limit], source="catalog")

    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            r = await client.get(_SEARCH_URL, params={"q": q})
            r.raise_for_status()
            names = list(dict.fromkeys(_LIBRARY_HREF.findall(r.text)))
    except Exception as exc:
        return LibraryResponse(
            results=curated[:limit],
            source="catalog",
            detail=f"Ollama library unreachable ({exc.__class__.__name__}); showing curated matches only.",
        )

    seen = {m.id.split(":")[0] for m in curated}
    results = list(curated)
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        card = catalog.on_prem_card(name)
        results.append(
            LibraryModel(
                id=name,
                name=card.name if card else name,
                description=card.summary if card else "",
                tags=[card.modality] if card else [],
                curated=card is not None,
            )
        )
    return LibraryResponse(results=results[:limit], source="ollama.com")
