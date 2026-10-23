from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


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


class EnterprisePolicyUpdate(BaseModel):
    enabled: Optional[bool] = None
    mode: Optional[PolicyMode] = None
    domains: Optional[List[DomainPolicy]] = None


class NiyanConfig(BaseModel):
    version: int = 1
    profile: str = "auto"
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
        return [m for m in self.models if m.enabled and self.provider_ready(m.provider)]


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ServiceStatus(BaseModel):
    name: str
    status: str
    healthy: bool = False
    detail: str = ""


class ServicesResponse(BaseModel):
    services: List[ServiceStatus]


class ModelInfo(BaseModel):
    id: str
    family: str = ""
    provider: str = "ollama"
    deployment: str = "local"
    enabled: bool = True
    installed: bool = False
    loaded: bool = False
    default: bool = False
    provider_ready: bool = True
    can_pull: bool = True


class ModelsResponse(BaseModel):
    models: List[ModelInfo]


class ModelUpdate(BaseModel):
    enabled: Optional[bool] = None
    default: Optional[bool] = None
    # Set when enabling a model that is not in niyan.yaml yet — e.g. one the
    # provider's /models endpoint reported that Niyan has no curated card for.
    provider: Optional[ModelProvider] = None
    family: Optional[str] = None


class PullRequest(BaseModel):
    name: str


class ProviderPublic(BaseModel):
    enabled: bool = False
    configured: bool = False
    api_key_last4: str = ""


class ProvidersPublic(BaseModel):
    openai: ProviderPublic = Field(default_factory=ProviderPublic)
    gemini: ProviderPublic = Field(default_factory=ProviderPublic)
    anthropic: ProviderPublic = Field(default_factory=ProviderPublic)


class ProviderUpdate(BaseModel):
    enabled: Optional[bool] = None
    api_key: Optional[str] = None


class ProvidersUpdate(BaseModel):
    openai: Optional[ProviderUpdate] = None
    gemini: Optional[ProviderUpdate] = None
    anthropic: Optional[ProviderUpdate] = None


class GuardrailsUpdate(BaseModel):
    enabled: Optional[bool] = None
    provider: Optional[GuardrailsProvider] = None
    on_failure: Optional[OnFailure] = None
    scanners: Optional[List[str]] = None
    output_scanners: Optional[List[str]] = None


class ObservabilityUpdate(BaseModel):
    enabled: Optional[bool] = None
    public_key: Optional[str] = None
    secret_key: Optional[str] = None
    host: Optional[str] = None


class VectorUpdate(BaseModel):
    enabled: Optional[bool] = None
    provider: Optional[VectorProvider] = None
    qdrant_port: Optional[int] = None
    pgvector_database: Optional[str] = None


class EmbeddingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    model: Optional[str] = None


class CollectionCreate(BaseModel):
    name: str
    size: int = Field(default=768, ge=1, description="Vector dimensions (nomic-embed-text=768)")


class VectorPoint(BaseModel):
    id: str
    vector: List[float]
    payload: Optional[dict] = None


class UpsertRequest(BaseModel):
    collection: str
    points: List[VectorPoint]


class SearchRequest(BaseModel):
    collection: str
    vector: List[float]
    limit: int = Field(default=5, ge=1, le=100)
