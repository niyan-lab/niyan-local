"""Tests for proprietary providers, LiteLLM gen, and pricing."""

from unittest.mock import patch

from niyan.config import ModelProvider, PricingConfig, load_config
from niyan.litellm_gen import build_litellm_config
from niyan.local_compose import find_repo_root
from niyan.pricing import estimate_cost_usd


def test_example_config_has_providers_and_proprietary_models():
    root = find_repo_root()
    cfg = load_config(root / "configs" / "niyan.example.yaml")
    assert cfg.providers.openai.enabled is False
    assert cfg.providers.gemini.api_key == ""
    ids = {m.id: m for m in cfg.models}
    assert ids["gpt-4o-mini"].provider == ModelProvider.openai
    assert ids["gemini-2.5-flash"].provider == ModelProvider.gemini
    assert ids["gemini-3.5-flash"].provider == ModelProvider.gemini
    assert ids["claude-sonnet-5"].provider == ModelProvider.anthropic
    assert ids["claude-haiku-4-5"].provider == ModelProvider.anthropic
    assert ids["claude-opus-5"].provider == ModelProvider.anthropic
    assert cfg.providers.anthropic.api_key == ""
    assert "gemini-2.0-flash" not in ids
    assert "gemini-1.5-flash" not in ids
    assert ids["llama3.2:3b"].provider == ModelProvider.ollama


def test_litellm_gen_ollama_only_without_keys():
    root = find_repo_root()
    cfg = load_config(root / "configs" / "niyan.example.yaml")
    # proprietary disabled / no keys — should not appear
    payload = build_litellm_config(cfg)
    names = [m["model_name"] for m in payload["model_list"]]
    assert "llama3.2:3b" in names
    assert "nomic-embed-text" in names
    assert "gpt-4o-mini" not in names
    assert "gemini-2.5-flash" not in names
    assert "claude-sonnet-5" not in names


def test_litellm_gen_includes_openai_when_ready():
    root = find_repo_root()
    cfg = load_config(root / "configs" / "niyan.example.yaml")
    cfg.providers.openai.enabled = True
    cfg.providers.openai.api_key = "sk-test-openai"
    for m in cfg.models:
        if m.id == "gpt-4o-mini":
            m.enabled = True
    payload = build_litellm_config(cfg)
    entry = next(m for m in payload["model_list"] if m["model_name"] == "gpt-4o-mini")
    assert entry["litellm_params"]["model"] == "openai/gpt-4o-mini"
    assert entry["litellm_params"]["api_key"] == "sk-test-openai"


def test_litellm_gen_includes_gemini_when_ready():
    root = find_repo_root()
    cfg = load_config(root / "configs" / "niyan.example.yaml")
    cfg.providers.gemini.enabled = True
    cfg.providers.gemini.api_key = "gem-test"
    for m in cfg.models:
        if m.id == "gemini-2.5-flash":
            m.enabled = True
    payload = build_litellm_config(cfg)
    entry = next(m for m in payload["model_list"] if m["model_name"] == "gemini-2.5-flash")
    assert entry["litellm_params"]["model"] == "gemini/gemini-2.5-flash"


def test_litellm_gen_includes_anthropic_when_ready():
    root = find_repo_root()
    cfg = load_config(root / "configs" / "niyan.example.yaml")
    cfg.providers.anthropic.enabled = True
    cfg.providers.anthropic.api_key = "sk-ant-test"
    for m in cfg.models:
        if m.id == "claude-sonnet-5":
            m.enabled = True
    payload = build_litellm_config(cfg)
    entry = next(m for m in payload["model_list"] if m["model_name"] == "claude-sonnet-5")
    assert entry["litellm_params"]["model"] == "anthropic/claude-sonnet-5"
    assert entry["litellm_params"]["api_key"] == "sk-ant-test"


def test_pricing_local_is_zero():
    assert estimate_cost_usd("ollama", "llama3.2:3b", 1000, 500) == 0.0


def test_pricing_openai_gpt4o_mini():
    cost = estimate_cost_usd("openai", "gpt-4o-mini", 1_000_000, 1_000_000, PricingConfig())
    assert abs(cost - (0.15 + 0.60)) < 1e-9


def test_pricing_anthropic_sonnet():
    cost = estimate_cost_usd("anthropic", "claude-sonnet-5", 1_000_000, 1_000_000, PricingConfig())
    assert abs(cost - (3.00 + 15.00)) < 1e-9


def test_metrics_snapshot_includes_tokens_and_cost():
    import sys
    from pathlib import Path

    gw = Path(__file__).resolve().parents[2] / "services" / "gateway"
    sys.path.insert(0, str(gw))
    import metrics as gw_metrics  # type: ignore

    # reset memory backend
    with gw_metrics._lock:
        gw_metrics._mem.clear()
    gw_metrics._redis = None
    gw_metrics._redis_tried = True  # force memory path

    gw_metrics.record(
        "chat",
        "gpt-4o-mini",
        12.5,
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        cost_usd=0.001,
        provider="openai",
        application="enterprise-functions",
    )
    snap = gw_metrics.snapshot()
    assert snap["totals"]["total_tokens"] >= 150
    assert snap["totals"]["cost_usd"] >= 0.001
    by = {m["model"]: m for m in snap["by_model"]}
    assert by["gpt-4o-mini"]["total_tokens"] == 150
    assert by["gpt-4o-mini"]["cost_usd"] == 0.001
    prov = {p["provider"]: p for p in snap["by_provider"]}
    assert prov["openai"]["total_tokens"] == 150
    apps = {a["id"]: a for a in snap["by_application"]}
    assert apps["enterprise-functions"]["total_tokens"] == 150

    gw_metrics.record(
        "chat",
        "gpt-4o-mini",
        8.0,
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        cost_usd=0.0001,
        provider="openai",
        application="project-xyz",
        domain="finance",
    )
    snap = gw_metrics.snapshot()
    apps = {a["id"]: a for a in snap["by_application"]}
    assert "project-xyz" not in apps
    assert apps["enterprise-functions"]["total_tokens"] == 165
    domains = {d["id"]: d for d in snap["by_domain"]}
    assert domains["finance"]["total_tokens"] == 15
