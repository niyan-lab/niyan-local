"""Curated model catalogs backing the Inference pages.

The JSON files next to this module are hand-maintained: adding a model card is a
data edit, not a code change. Benchmark figures are transcribed from each
publisher's own model card or paper (see `source_url`) and are not re-run here.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

from app.schemas.catalog import ModelCard, ProprietaryModelCard

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _normalize(model_id: str) -> str:
    """Ollama treats a bare name as `name:latest`; match on the bare name."""
    return (model_id or "").strip().lower().split(":")[0]


@lru_cache(maxsize=1)
def on_prem_cards() -> List[ModelCard]:
    raw = json.loads((_DATA_DIR / "on_prem_models.json").read_text())
    return [ModelCard.model_validate(item) for item in raw]


@lru_cache(maxsize=1)
def _on_prem_index() -> Dict[str, ModelCard]:
    index: Dict[str, ModelCard] = {}
    for card in on_prem_cards():
        index[card.id.lower()] = card
        index.setdefault(_normalize(card.id), card)
    return index


def on_prem_card(model_id: str) -> Optional[ModelCard]:
    """Exact tag match first, then the bare name (`llama3.2` → `llama3.2:3b`)."""
    index = _on_prem_index()
    key = (model_id or "").strip().lower()
    return index.get(key) or index.get(_normalize(key))


@lru_cache(maxsize=1)
def proprietary_cards() -> List[ProprietaryModelCard]:
    raw = json.loads((_DATA_DIR / "proprietary_models.json").read_text())
    return [ProprietaryModelCard.model_validate(item) for item in raw]


@lru_cache(maxsize=1)
def _proprietary_index() -> Dict[str, ProprietaryModelCard]:
    return {card.id.lower(): card for card in proprietary_cards()}


def proprietary_card(model_id: str) -> Optional[ProprietaryModelCard]:
    return _proprietary_index().get((model_id or "").strip().lower())


def proprietary_cards_for(provider: str) -> List[ProprietaryModelCard]:
    name = (provider or "").strip().lower()
    return [card for card in proprietary_cards() if card.provider == name]
