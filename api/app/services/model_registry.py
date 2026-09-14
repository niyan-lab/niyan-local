"""Reconcile niyan.yaml's model list with what Ollama actually has on disk.

Models pulled straight through Ollama (`ollama pull …`, or another tool sharing
the volume) are adopted into the config automatically so the On-prem page and
the gateway agree on what exists.
"""

from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional

from app.schemas.models import ModelEntry, ModelProvider, NiyanConfig
from app.services import catalog, config_manager

log = logging.getLogger(__name__)


def normalize(model_id: str) -> str:
    """`llama3.2:latest` and `llama3.2` are the same Ollama model."""
    name = (model_id or "").strip()
    return name[: -len(":latest")] if name.endswith(":latest") else name


def _is_embedding(model_id: str, ollama_family: str = "") -> bool:
    card = catalog.on_prem_card(model_id)
    if card is not None:
        return card.modality == "embedding"
    haystack = f"{model_id} {ollama_family}".lower()
    return "embed" in haystack


def _family_for(model_id: str, ollama_family: str = "") -> str:
    card = catalog.on_prem_card(model_id)
    if card is not None:
        return card.family
    if ollama_family:
        return ollama_family
    return normalize(model_id).split(":")[0]


def adopt_discovered(
    config: NiyanConfig,
    discovered: Iterable[Dict[str, object]],
) -> List[str]:
    """Append Ollama-only models to the config. Returns the ids that were added.

    Embedding models are adopted disabled: they are served through the
    embeddings config rather than as chat routes, and enabling them would put
    them in the gateway's chat model list.
    """
    known = {normalize(m.id) for m in config.models}
    known.add(normalize(config.embeddings.model or ""))
    adopted: List[str] = []

    for item in discovered:
        raw_id = str(item.get("id") or "")
        model_id = normalize(raw_id)
        if not model_id or model_id in known:
            continue
        known.add(model_id)
        ollama_family = str(item.get("family") or "")
        config.models.append(
            ModelEntry(
                id=model_id,
                provider=ModelProvider.ollama,
                family=_family_for(model_id, ollama_family),
                enabled=not _is_embedding(model_id, ollama_family),
                default=False,
            )
        )
        adopted.append(model_id)

    return adopted


def persist_adoptions(config: NiyanConfig, adopted: List[str]) -> None:
    """Save the config and refresh LiteLLM routing after an adoption.

    Best-effort: a read-only config mount (Kubernetes) or a stopped LiteLLM must
    not break the page that triggered the reconcile.
    """
    if not adopted:
        return
    try:
        config_manager.save_config(config)
    except Exception:
        log.warning("could not persist adopted models %s", adopted, exc_info=True)
        return
    try:
        from app.services.litellm_gen import apply_provider_changes

        apply_provider_changes(config)
    except Exception:
        log.warning("adopted %s but LiteLLM refresh failed", adopted, exc_info=True)


def find_entry(config: NiyanConfig, model_id: str) -> Optional[ModelEntry]:
    target = normalize(model_id)
    return next((m for m in config.models if normalize(m.id) == target), None)


def ensure_local_model(config: NiyanConfig, model_id: str) -> bool:
    """Make sure a pull target exists in niyan.yaml. Returns True if added."""
    name = normalize(model_id)
    if not name or find_entry(config, name) is not None:
        return False
    if normalize(config.embeddings.model or "") == name:
        return False
    config.models.append(
        ModelEntry(
            id=name,
            provider=ModelProvider.ollama,
            family=_family_for(name),
            enabled=not _is_embedding(name),
            default=False,
        )
    )
    return True
