"""Estimate USD API cost from token usage and niyan pricing table."""

from __future__ import annotations

from typing import Any, Dict, Optional, Union

from niyan.config import ModelProvider, NiyanConfig, PricingConfig


def estimate_cost_usd(
    provider: Union[str, ModelProvider],
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    pricing: Optional[PricingConfig] = None,
) -> float:
    """Return estimated API cost in USD. Local/ollama is always 0."""
    prov = provider.value if isinstance(provider, ModelProvider) else str(provider or "ollama")
    if prov in {"ollama", "local", ""}:
        return 0.0
    pricing = pricing or PricingConfig()
    if prov == "openai":
        table = pricing.openai
    elif prov == "gemini":
        table = pricing.gemini
    elif prov == "anthropic":
        table = pricing.anthropic
    else:
        table = {}
    entry = table.get(model)
    if entry is None:
        return 0.0
    if isinstance(entry, dict):
        inp = float(entry.get("input_per_1m") or 0)
        out = float(entry.get("output_per_1m") or 0)
    else:
        inp = float(entry.input_per_1m)
        out = float(entry.output_per_1m)
    return (max(0, prompt_tokens) / 1_000_000.0) * inp + (max(0, completion_tokens) / 1_000_000.0) * out


def cost_from_usage(
    config: NiyanConfig,
    model: str,
    usage: Optional[Dict[str, Any]],
    provider: Optional[str] = None,
) -> float:
    if not usage:
        return 0.0
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    prov = provider
    if not prov:
        for m in config.models:
            if m.id == model:
                prov = m.provider.value
                break
        else:
            prov = "ollama"
    return estimate_cost_usd(prov, model, prompt, completion, config.pricing)


def pricing_json(config: NiyanConfig) -> Dict[str, Any]:
    return config.pricing.model_dump(mode="json")


def model_providers_map(config: NiyanConfig) -> Dict[str, str]:
    out = {m.id: m.provider.value for m in config.models}
    if config.embeddings.enabled and config.embeddings.model:
        out.setdefault(config.embeddings.model, "ollama")
    return out
