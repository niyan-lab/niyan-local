from __future__ import annotations

import yaml

from app.schemas.models import (
    DomainPolicy,
    EnterprisePolicyConfig,
    ModelEntry,
    ModelProvider,
    NiyanConfig,
    PricingConfig,
    SEED_DOMAIN_IDS,
    default_domain_policies,
)
from app.settings import settings

CURATED_MODELS = [
    ModelEntry(id="llama3.2:3b", provider=ModelProvider.ollama, family="llama", enabled=True, default=True),
    ModelEntry(id="gemma2:2b", provider=ModelProvider.ollama, family="gemma", enabled=True),
    ModelEntry(id="gpt-4o-mini", provider=ModelProvider.openai, family="gpt", enabled=False),
    ModelEntry(id="gpt-4o", provider=ModelProvider.openai, family="gpt", enabled=False),
    ModelEntry(id="gemini-2.5-flash", provider=ModelProvider.gemini, family="gemini", enabled=False),
    ModelEntry(id="gemini-3.5-flash", provider=ModelProvider.gemini, family="gemini", enabled=False),
    ModelEntry(id="claude-haiku-4-5", provider=ModelProvider.anthropic, family="claude", enabled=False),
    ModelEntry(id="claude-sonnet-5", provider=ModelProvider.anthropic, family="claude", enabled=False),
    ModelEntry(id="claude-opus-5", provider=ModelProvider.anthropic, family="claude", enabled=False),
]

DEPRECATED_MODEL_IDS = frozenset({"gemini-1.5-flash", "gemini-2.0-flash"})


def ensure_enterprise_policy(config: NiyanConfig) -> bool:
    """Seed missing default domains on older niyan.yaml files. Returns True if changed."""
    changed = False
    if config.enterprise_policy is None:
        config.enterprise_policy = EnterprisePolicyConfig()
        return True
    existing = {d.id.lower() for d in config.enterprise_policy.domains}
    for domain_id in SEED_DOMAIN_IDS:
        if domain_id not in existing:
            config.enterprise_policy.domains.append(DomainPolicy(id=domain_id))
            changed = True
    if not config.enterprise_policy.domains:
        config.enterprise_policy.domains = default_domain_policies()
        changed = True
    return changed


def ensure_curated_models(config: NiyanConfig) -> NiyanConfig:
    """Append curated proprietary/local models missing from older niyan.yaml files."""
    config.models = [m for m in config.models if m.id not in DEPRECATED_MODEL_IDS]
    existing = {m.id for m in config.models}
    changed = False
    for m in CURATED_MODELS:
        if m.id not in existing:
            entry = m.model_copy(update={"enabled": False, "default": False})
            if m.provider == ModelProvider.ollama and not config.models:
                entry.enabled = True
                entry.default = True
            config.models.append(entry)
            changed = True
    for stale in DEPRECATED_MODEL_IDS:
        if stale in config.pricing.gemini:
            config.pricing.gemini.pop(stale, None)
            changed = True
    defaults = PricingConfig().gemini
    for m in CURATED_MODELS:
        if m.provider == ModelProvider.gemini and m.id not in config.pricing.gemini:
            if m.id in defaults:
                config.pricing.gemini[m.id] = defaults[m.id]
                changed = True
    anthro_defaults = PricingConfig().anthropic
    for m in CURATED_MODELS:
        if m.provider == ModelProvider.anthropic and m.id not in config.pricing.anthropic:
            if m.id in anthro_defaults:
                config.pricing.anthropic[m.id] = anthro_defaults[m.id]
                changed = True
    if ensure_enterprise_policy(config):
        changed = True
    if changed and settings.niyan_config_path.exists():
        save_config(config)
    return config


def load_config() -> NiyanConfig:
    path = settings.niyan_config_path
    if not path.exists():
        example = settings.niyan_root / "configs" / "niyan.example.yaml"
        if example.exists():
            data = yaml.safe_load(example.read_text()) or {}
            return ensure_curated_models(NiyanConfig.model_validate(data))
        return ensure_curated_models(NiyanConfig())
    data = yaml.safe_load(path.read_text()) or {}
    return ensure_curated_models(NiyanConfig.model_validate(data))


def save_config(config: NiyanConfig) -> NiyanConfig:
    path = settings.niyan_config_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False))
    return config
