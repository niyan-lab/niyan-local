"""Niyan control plane settings."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    niyan_root: Path = Path("/niyan")
    niyan_config_path: Path = Path("/niyan/niyan.yaml")
    niyan_admin_username: str = "admin"
    niyan_admin_password: str = "niyan"
    niyan_jwt_secret: str = "change-me-niyan-dev-secret"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 12

    ollama_host: str = "http://ollama:11434"
    litellm_url: str = "http://litellm:4001"
    gateway_url: str = "http://gateway:4000"
    litellm_master_key: str = "sk-niyan-local"
    langfuse_url: str = "http://langfuse-web:3000"
    guardrails_provider: str = "llm_guard"
    guard_llm_url: str = "http://guardrails:8088"
    guard_nemo_url: str = "http://nemo-guardrails:8089"

    vector_enabled: bool = False
    vector_provider: str = "qdrant"
    qdrant_url: str = "http://qdrant:6333"
    pgvector_dsn: str = "postgresql://niyan:niyan@postgres:5432/niyan_vectors"
    embeddings_enabled: bool = True
    embeddings_model: str = "nomic-embed-text"


settings = Settings()
