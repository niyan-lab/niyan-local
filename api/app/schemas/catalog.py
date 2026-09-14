"""Model card schemas for the Inference pages (on-prem + proprietary)."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class Benchmark(BaseModel):
    """A single published benchmark figure.

    Scores are transcribed from the publisher's own model card or paper and are
    not re-run by Niyan, so `note` carries the shot/eval setting that makes the
    number comparable.
    """

    suite: str
    score: float
    unit: str = "%"
    note: str = ""


class SystemRequirements(BaseModel):
    """Sizing for the default quantization Ollama pulls for this tag."""

    quantization: str = "Q4_K_M"
    disk_gb: float
    min_ram_gb: float
    recommended_ram_gb: float
    min_vram_gb: float = 0.0
    runs_on_cpu: bool = True
    note: str = ""


class ModelCard(BaseModel):
    """Curated descriptive metadata for a self-hosted model tag."""

    id: str
    name: str
    family: str
    publisher: str
    parameters: str
    context_window: int
    license: str
    modality: str = "chat"
    summary: str
    strengths: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    benchmarks: List[Benchmark] = Field(default_factory=list)
    requirements: SystemRequirements
    source_url: str = ""
    embedding_dimensions: Optional[int] = None


class ProprietaryModelCard(BaseModel):
    """Curated descriptive metadata for a cloud provider model."""

    id: str
    name: str
    provider: str
    family: str
    context_window: int
    max_output_tokens: Optional[int] = None
    modality: str = "chat"
    summary: str
    strengths: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    input_per_1m: float = 0.0
    output_per_1m: float = 0.0
    source_url: str = ""


class OnPremModel(BaseModel):
    """A self-hosted model as shown on the On-prem page.

    Merges three sources: the `models:` list in niyan.yaml, what Ollama reports
    on disk / in memory, and the curated catalog card (absent for models pulled
    straight from the Ollama library).
    """

    id: str
    family: str = ""
    enabled: bool = False
    installed: bool = False
    loaded: bool = False
    default: bool = False
    managed: bool = True
    size_bytes: Optional[int] = None
    parameter_size: str = ""
    quantization: str = ""
    modified_at: str = ""
    card: Optional[ModelCard] = None


class OnPremResponse(BaseModel):
    models: List[OnPremModel] = Field(default_factory=list)
    adopted: List[str] = Field(default_factory=list)
    ollama_reachable: bool = True


class CatalogResponse(BaseModel):
    """Curated cards for models that are not installed yet."""

    cards: List[ModelCard] = Field(default_factory=list)


class LibraryModel(BaseModel):
    """A search hit from the public Ollama library."""

    id: str
    name: str
    description: str = ""
    tags: List[str] = Field(default_factory=list)
    pulls: str = ""
    curated: bool = False


class LibraryResponse(BaseModel):
    results: List[LibraryModel] = Field(default_factory=list)
    source: str = "catalog"
    detail: str = ""


class ProviderModel(BaseModel):
    """A proprietary model as shown on the Proprietary page."""

    id: str
    name: str = ""
    provider: str
    family: str = ""
    enabled: bool = False
    default: bool = False
    configured: bool = False
    in_config: bool = True
    available_live: Optional[bool] = None
    card: Optional[ProprietaryModelCard] = None


class ProviderSection(BaseModel):
    name: str
    title: str
    docs_url: str = ""
    enabled: bool = False
    configured: bool = False
    api_key_last4: str = ""
    models: List[ProviderModel] = Field(default_factory=list)
    live_refreshed: bool = False
    detail: str = ""


class ProprietaryResponse(BaseModel):
    providers: List[ProviderSection] = Field(default_factory=list)
