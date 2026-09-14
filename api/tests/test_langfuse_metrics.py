"""Unit tests for Langfuse daily metrics aggregation."""

from app.schemas.models import ModelEntry, ModelProvider, NiyanConfig
from app.services.langfuse_metrics import aggregate_daily, classify_provider, resolve_range


def test_resolve_range_presets():
    fr, to, label = resolve_range("7d")
    assert label == "7d"
    assert (to - fr).days == 7


def test_classify_provider():
    mapping = {"llama3.2:3b": "ollama", "gpt-4o-mini": "openai"}
    assert classify_provider("gpt-4o-mini", mapping) == "openai"
    assert classify_provider("gemini-2.5-flash", {}) == "gemini"
    assert classify_provider("claude-sonnet-5", {}) == "anthropic"
    assert classify_provider("llama3.2:3b", mapping) == "ollama"


def test_aggregate_daily_proprietary_cost():
    cfg = NiyanConfig(
        models=[
            ModelEntry(id="llama3.2:3b", provider=ModelProvider.ollama, family="llama"),
            ModelEntry(id="gemini-2.5-flash", provider=ModelProvider.gemini, family="gemini"),
            ModelEntry(id="gpt-4o-mini", provider=ModelProvider.openai, family="gpt"),
        ]
    )
    days = [
        {
            "date": "2026-07-18",
            "countTraces": 3,
            "totalCost": 0.05,
            "usage": [
                {
                    "model": "gemini-2.5-flash",
                    "inputUsage": 100,
                    "outputUsage": 50,
                    "totalUsage": 150,
                    "countTraces": 2,
                    "totalCost": 0.04,
                },
                {
                    "model": "llama3.2:3b",
                    "inputUsage": 200,
                    "outputUsage": 20,
                    "totalUsage": 220,
                    "countTraces": 1,
                    "totalCost": 0.0,
                },
            ],
        }
    ]
    agg = aggregate_daily(days, cfg)
    assert agg["source"] == "langfuse"
    assert agg["period"]["total_tokens"] == 370
    assert abs(agg["period"]["cost_usd"] - 0.04) < 1e-9
    assert agg["comparison"]["proprietary"]["cost_usd"] == 0.04
    assert agg["comparison"]["local"]["cost_usd"] is None
    assert agg["comparison"]["local"]["tokens"] == 220
    models = {m["model"]: m for m in agg["by_model"]}
    assert models["gemini-2.5-flash"]["cost_usd"] == 0.04
    assert models["llama3.2:3b"]["cost_usd"] is None
