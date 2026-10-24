"""Shared Niyan configuration schema (niyan.yaml)."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator


class Profile(str, Enum):
    auto = "auto"
    mac = "mac"
    windows = "windows"
    linux_cpu = "linux-cpu"
    linux_gpu = "linux-gpu"


def uses_host_ollama(profile: Profile) -> bool:
    """Mac and Windows use Docker Desktop + host Ollama via host.docker.internal."""
    return profile in {Profile.mac, Profile.windows}


class ModelProvider(str, Enum):
    ollama = "ollama"
    openai = "openai"
    gemini = "gemini"
    anthropic = "anthropic"
    vllm = "vllm"


PROPRIETARY_PROVIDERS = frozenset(
    {ModelProvider.openai, ModelProvider.gemini, ModelProvider.anthropic}
)


class GuardrailsProvider(str, Enum):
    llm_guard = "llm_guard"
    nemo = "nemo"


class VectorProvider(str, Enum):
    qdrant = "qdrant"
    pgvector = "pgvector"


class OnFailure(str, Enum):
    allow = "allow"
    block = "block"


class ModelEntry(BaseModel):
    id: str
    provider: ModelProvider = ModelProvider.ollama
    family: str = "llama"
    enabled: bool = True
    default: bool = False

    @property
    def deployment(self) -> str:
        if self.provider == ModelProvider.ollama:
            return "local"
        if self.provider == ModelProvider.vllm:
            return "self-hosted"
        return "proprietary"


class ProxyConfig(BaseModel):
    port: int = 4000
    api_keys: List[str] = Field(default_factory=list)


class ObservabilityConfig(BaseModel):
    enabled: bool = True
    provider: str = "langfuse"
    public_key: str = ""
    secret_key: str = ""
    host: str = "http://langfuse:3000"


class LlmGuardConfig(BaseModel):
    scanners: List[str] = Field(default_factory=lambda: ["prompt_injection", "pii"])
    output_scanners: List[str] = Field(default_factory=lambda: ["pii", "toxicity", "secrets"])


class NemoConfig(BaseModel):
    config_path: str = "./services/nemo/config.yml"


class GuardrailsConfig(BaseModel):
    enabled: bool = True
    provider: GuardrailsProvider = GuardrailsProvider.llm_guard
    on_failure: OnFailure = OnFailure.allow
    llm_guard: LlmGuardConfig = Field(default_factory=LlmGuardConfig)
    nemo: NemoConfig = Field(default_factory=NemoConfig)


class AdminConfig(BaseModel):
    enabled: bool = True
    port: int = 3080


class ApiConfig(BaseModel):
    port: int = 8100


class OllamaConfig(BaseModel):
    host: str = "http://ollama:11434"


class AdminAuthConfig(BaseModel):
    username: str = "admin"
    password: str = ""
    jwt_secret: str = ""


class EmbeddingsConfig(BaseModel):
    enabled: bool = True
    model: str = "nomic-embed-text"


class QdrantConfig(BaseModel):
    port: int = 6333


class PgvectorConfig(BaseModel):
    database: str = "niyan_vectors"


class VectorConfig(BaseModel):
    enabled: bool = False
    provider: VectorProvider = VectorProvider.qdrant
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)
    pgvector: PgvectorConfig = Field(default_factory=PgvectorConfig)


class ProviderCredentials(BaseModel):
    enabled: bool = False
    api_key: str = ""
    api_base: str = ""


class ProvidersConfig(BaseModel):
    openai: ProviderCredentials = Field(default_factory=ProviderCredentials)
    gemini: ProviderCredentials = Field(default_factory=ProviderCredentials)
    anthropic: ProviderCredentials = Field(default_factory=ProviderCredentials)
    vllm: ProviderCredentials = Field(default_factory=ProviderCredentials)


class ModelPrice(BaseModel):
    input_per_1m: float = 0.0
    output_per_1m: float = 0.0


class PricingConfig(BaseModel):
    openai: Dict[str, ModelPrice] = Field(
        default_factory=lambda: {
            "gpt-4o-mini": ModelPrice(input_per_1m=0.15, output_per_1m=0.60),
            "gpt-4o": ModelPrice(input_per_1m=2.50, output_per_1m=10.00),
        }
    )
    gemini: Dict[str, ModelPrice] = Field(
        default_factory=lambda: {
            "gemini-2.5-flash": ModelPrice(input_per_1m=0.30, output_per_1m=2.50),
            "gemini-3.5-flash": ModelPrice(input_per_1m=1.50, output_per_1m=9.00),
        }
    )
    anthropic: Dict[str, ModelPrice] = Field(
        default_factory=lambda: {
            "claude-haiku-4-5": ModelPrice(input_per_1m=1.00, output_per_1m=5.00),
            "claude-sonnet-5": ModelPrice(input_per_1m=3.00, output_per_1m=15.00),
            "claude-opus-5": ModelPrice(input_per_1m=15.00, output_per_1m=75.00),
        }
    )
    local_estimate_per_1m_tokens: Optional[float] = None


class PolicyDeployment(str, Enum):
    local = "local"
    proprietary = "proprietary"


class PolicyMode(str, Enum):
    manual = "manual"
    auto = "auto"


SEED_DOMAIN_IDS = (
    "finance",
    "marketing",
    "sales",
    "research",
    "summary",
    "support",
    "legal",
)

DEFAULT_LOCAL_MODEL = "llama3.2:3b"
DEFAULT_PROPRIETARY_MODEL = "gemini-2.5-flash"


class DomainPolicy(BaseModel):
    id: str
    enabled: bool = True
    deployment: PolicyDeployment = PolicyDeployment.local
    local_model: str = DEFAULT_LOCAL_MODEL
    proprietary_model: str = DEFAULT_PROPRIETARY_MODEL


def default_domain_policies() -> List[DomainPolicy]:
    return [DomainPolicy(id=domain_id) for domain_id in SEED_DOMAIN_IDS]


class EnterprisePolicyConfig(BaseModel):
    enabled: bool = True
    mode: PolicyMode = PolicyMode.manual
    domains: List[DomainPolicy] = Field(default_factory=default_domain_policies)


class NiyanConfig(BaseModel):
    version: int = 1
    profile: Profile = Profile.auto
    models: List[ModelEntry] = Field(default_factory=list)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    pricing: PricingConfig = Field(default_factory=PricingConfig)
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    guardrails: GuardrailsConfig = Field(default_factory=GuardrailsConfig)
    embeddings: EmbeddingsConfig = Field(default_factory=EmbeddingsConfig)
    vector: VectorConfig = Field(default_factory=VectorConfig)
    enterprise_policy: EnterprisePolicyConfig = Field(default_factory=EnterprisePolicyConfig)
    admin: AdminConfig = Field(default_factory=AdminConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    admin_auth: AdminAuthConfig = Field(default_factory=AdminAuthConfig)

    @field_validator("models")
    @classmethod
    def at_least_one_enabled_when_present(cls, models: List[ModelEntry]) -> List[ModelEntry]:
        if models and not any(m.enabled for m in models):
            raise ValueError("At least one model must be enabled")
        return models

    def enabled_models(self) -> List[ModelEntry]:
        return [m for m in self.models if m.enabled]

    def default_model(self) -> Optional[ModelEntry]:
        for m in self.enabled_models():
            if m.default:
                return m
        enabled = self.enabled_models()
        return enabled[0] if enabled else None

    def provider_ready(self, provider: ModelProvider) -> bool:
        if provider == ModelProvider.ollama:
            return True
        if provider == ModelProvider.openai:
            return bool(self.providers.openai.enabled and self.providers.openai.api_key.strip())
        if provider == ModelProvider.gemini:
            return bool(self.providers.gemini.enabled and self.providers.gemini.api_key.strip())
        if provider == ModelProvider.anthropic:
            return bool(self.providers.anthropic.enabled and self.providers.anthropic.api_key.strip())
        if provider == ModelProvider.vllm:
            return bool(self.providers.vllm.enabled and self.providers.vllm.api_base.strip())
        return False

    def routable_models(self) -> List[ModelEntry]:
        """Enabled models whose provider credentials are ready."""
        return [m for m in self.enabled_models() if self.provider_ready(m.provider)]


def load_config(path: Path) -> NiyanConfig:
    data = yaml.safe_load(path.read_text()) or {}
    return ensure_curated_models(NiyanConfig.model_validate(data))


def save_config(path: Path, config: NiyanConfig) -> None:
    payload = config.model_dump(mode="json")
    path.write_text(yaml.safe_dump(payload, sort_keys=False))


CURATED_MODELS = [
    ModelEntry(
        id="llama3.2:3b",
        provider=ModelProvider.ollama,
        family="llama",
        enabled=True,
        default=True,
    ),
    ModelEntry(id="gemma2:2b", provider=ModelProvider.ollama, family="gemma", enabled=True),
    ModelEntry(id="gpt-4o-mini", provider=ModelProvider.openai, family="gpt", enabled=False),
    ModelEntry(id="gpt-4o", provider=ModelProvider.openai, family="gpt", enabled=False),
    ModelEntry(
        id="gemini-2.5-flash",
        provider=ModelProvider.gemini,
        family="gemini",
        enabled=False,
    ),
    ModelEntry(
        id="gemini-3.5-flash",
        provider=ModelProvider.gemini,
        family="gemini",
        enabled=False,
    ),
    ModelEntry(
        id="claude-haiku-4-5",
        provider=ModelProvider.anthropic,
        family="claude",
        enabled=False,
    ),
    ModelEntry(
        id="claude-sonnet-5",
        provider=ModelProvider.anthropic,
        family="claude",
        enabled=False,
    ),
    ModelEntry(
        id="claude-opus-5",
        provider=ModelProvider.anthropic,
        family="claude",
        enabled=False,
    ),
]

DEPRECATED_MODEL_IDS = frozenset({"gemini-1.5-flash", "gemini-2.0-flash"})


def ensure_curated_models(config: NiyanConfig) -> NiyanConfig:
    """Drop deprecated Gemini ids and append curated models missing from older yaml."""
    config.models = [m for m in config.models if m.id not in DEPRECATED_MODEL_IDS]
    existing = {m.id for m in config.models}
    for m in CURATED_MODELS:
        if m.id not in existing:
            entry = m.model_copy(update={"enabled": False, "default": False})
            config.models.append(entry)
    for stale in DEPRECATED_MODEL_IDS:
        config.pricing.gemini.pop(stale, None)
    defaults = PricingConfig().gemini
    for m in CURATED_MODELS:
        if m.provider == ModelProvider.gemini and m.id not in config.pricing.gemini:
            if m.id in defaults:
                config.pricing.gemini[m.id] = defaults[m.id]
    anthro_defaults = PricingConfig().anthropic
    for m in CURATED_MODELS:
        if m.provider == ModelProvider.anthropic and m.id not in config.pricing.anthropic:
            if m.id in anthro_defaults:
                config.pricing.anthropic[m.id] = anthro_defaults[m.id]
    existing_domains = {d.id.lower() for d in config.enterprise_policy.domains}
    for domain_id in SEED_DOMAIN_IDS:
        if domain_id not in existing_domains:
            config.enterprise_policy.domains.append(DomainPolicy(id=domain_id))
    if not config.enterprise_policy.domains:
        config.enterprise_policy.domains = default_domain_policies()
    return config


def default_example_config() -> NiyanConfig:
    return NiyanConfig(models=list(CURATED_MODELS))
