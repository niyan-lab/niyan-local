"""Adoption of models pulled straight through Ollama into niyan.yaml."""

from __future__ import annotations

from app.schemas.models import ModelEntry, ModelProvider, NiyanConfig
from app.services import catalog, model_registry


def _config(*ids: str) -> NiyanConfig:
    cfg = NiyanConfig()
    cfg.models = [
        ModelEntry(id=i, provider=ModelProvider.ollama, family="llama") for i in ids
    ]
    return cfg


def test_adopts_model_missing_from_config():
    cfg = _config("llama3.2:3b")
    adopted = model_registry.adopt_discovered(
        cfg, [{"id": "llama3.2:3b"}, {"id": "qwen2.5:7b"}]
    )
    assert adopted == ["qwen2.5:7b"]
    entry = model_registry.find_entry(cfg, "qwen2.5:7b")
    assert entry is not None
    assert entry.provider == ModelProvider.ollama
    assert entry.enabled is True
    assert entry.default is False


def test_adoption_is_idempotent():
    cfg = _config("llama3.2:3b")
    first = model_registry.adopt_discovered(cfg, [{"id": "qwen2.5:7b"}])
    second = model_registry.adopt_discovered(cfg, [{"id": "qwen2.5:7b"}])
    assert first == ["qwen2.5:7b"]
    assert second == []
    assert len([m for m in cfg.models if m.id == "qwen2.5:7b"]) == 1


def test_latest_suffix_matches_bare_config_entry():
    """Ollama reports `nomic-embed-text:latest` for a config entry without a tag."""
    cfg = _config("llama3.2:3b")
    adopted = model_registry.adopt_discovered(cfg, [{"id": "llama3.2:3b:latest"}])
    assert adopted == ["llama3.2:3b:latest"] or adopted == []

    cfg2 = _config("mistral")
    assert model_registry.adopt_discovered(cfg2, [{"id": "mistral:latest"}]) == []


def test_embedding_models_adopted_but_not_routed():
    """Embeddings are served through the embeddings config, not the chat model list."""
    cfg = _config("llama3.2:3b")
    cfg.embeddings.model = "nomic-embed-text"
    adopted = model_registry.adopt_discovered(cfg, [{"id": "mxbai-embed-large"}])
    assert adopted == ["mxbai-embed-large"]
    entry = model_registry.find_entry(cfg, "mxbai-embed-large")
    assert entry is not None
    assert entry.enabled is False


def test_configured_embeddings_model_is_not_re_adopted():
    cfg = _config("llama3.2:3b")
    cfg.embeddings.model = "nomic-embed-text"
    assert model_registry.adopt_discovered(cfg, [{"id": "nomic-embed-text:latest"}]) == []


def test_family_comes_from_catalog_then_ollama():
    cfg = _config()
    model_registry.adopt_discovered(
        cfg, [{"id": "qwen2.5-coder:7b"}, {"id": "some-custom-model", "family": "custom"}]
    )
    assert model_registry.find_entry(cfg, "qwen2.5-coder:7b").family == "qwen"
    assert model_registry.find_entry(cfg, "some-custom-model").family == "custom"


def test_uncatalogued_model_is_still_adopted():
    cfg = _config()
    adopted = model_registry.adopt_discovered(cfg, [{"id": "my-org/finetune:v3"}])
    assert adopted == ["my-org/finetune:v3"]
    assert model_registry.find_entry(cfg, "my-org/finetune:v3").enabled is True


def test_catalog_lookup_falls_back_to_bare_name():
    assert catalog.on_prem_card("llama3.2:3b").family == "llama"
    assert catalog.on_prem_card("nomic-embed-text:latest").modality == "embedding"
    assert catalog.on_prem_card("not-a-real-model") is None


def test_ensure_local_model_registers_catalog_pulls():
    cfg = _config("llama3.2:3b")
    assert model_registry.ensure_local_model(cfg, "phi3:3.8b") is True
    assert model_registry.find_entry(cfg, "phi3:3.8b").family == "phi"
    assert model_registry.ensure_local_model(cfg, "phi3:3.8b") is False
    assert model_registry.ensure_local_model(cfg, "llama3.2:3b") is False
