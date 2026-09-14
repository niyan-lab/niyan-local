"""Estimate USD cost inside the gateway from env-injected pricing JSON."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

_DEFAULT_PRICING = {
    "openai": {
        "gpt-4o-mini": {"input_per_1m": 0.15, "output_per_1m": 0.60},
        "gpt-4o": {"input_per_1m": 2.50, "output_per_1m": 10.00},
    },
    "gemini": {
        "gemini-2.5-flash": {"input_per_1m": 0.30, "output_per_1m": 2.50},
        "gemini-3.5-flash": {"input_per_1m": 1.50, "output_per_1m": 9.00},
    },
    "anthropic": {
        "claude-haiku-4-5": {"input_per_1m": 1.00, "output_per_1m": 5.00},
        "claude-sonnet-5": {"input_per_1m": 3.00, "output_per_1m": 15.00},
        "claude-opus-5": {"input_per_1m": 15.00, "output_per_1m": 75.00},
    },
}


def _pricing() -> Dict[str, Any]:
    raw = os.getenv("NIYAN_PRICING_JSON", "").strip()
    if not raw:
        return _DEFAULT_PRICING
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else _DEFAULT_PRICING
    except Exception:
        return _DEFAULT_PRICING


def _providers() -> Dict[str, str]:
    raw = os.getenv("NIYAN_MODEL_PROVIDERS", "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def resolve_provider(model: str) -> str:
    mapping = _providers()
    if model in mapping:
        return str(mapping[model])
    # Heuristics
    mid = (model or "").lower()
    if mid.startswith("gpt-") or mid.startswith("o1") or mid.startswith("o3"):
        return "openai"
    if mid.startswith("gemini"):
        return "gemini"
    if mid.startswith("claude") or "anthropic" in mid:
        return "anthropic"
    return "ollama"


def estimate_cost_usd(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    provider: Optional[str] = None,
    response_cost: Optional[float] = None,
) -> float:
    if response_cost is not None:
        try:
            return max(0.0, float(response_cost))
        except Exception:
            pass
    prov = provider or resolve_provider(model)
    if prov in {"ollama", "local", ""}:
        return 0.0
    table = _pricing().get(prov) or {}
    entry = table.get(model) or {}
    inp = float(entry.get("input_per_1m") or 0)
    out = float(entry.get("output_per_1m") or 0)
    return (max(0, prompt_tokens) / 1_000_000.0) * inp + (max(0, completion_tokens) / 1_000_000.0) * out


def usage_tokens(usage: Optional[Dict[str, Any]]) -> tuple[int, int, int]:
    if not usage:
        return 0, 0, 0
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    total = int(usage.get("total_tokens") or (prompt + completion))
    return prompt, completion, total
