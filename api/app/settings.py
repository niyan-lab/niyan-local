"""Niyan control plane settings."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    niyan_root: Path = Path("/niyan")
    niyan_config_path: Path = Path("/niyan/niyan.yaml")
    # Empty DSN + empty PGHOST → file-only store (unit tests / first boot without Postgres).
    niyan_config_dsn: str = ""
    niyan_config_pghost: str = ""
    niyan_config_pgport: int = 5432
    niyan_config_pguser: str = "niyan"
    niyan_config_pgdatabase: str = "niyan"
    niyan_config_pgpassword: str = ""
    redis_host: str = ""
    redis_port: int = 6379
    niyan_admin_username: str = "admin"
    niyan_admin_password: str = ""
    niyan_jwt_secret: str = ""
    niyan_allow_insecure_defaults: bool = False
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 12
    niyan_cors_origins: str = ""

    ollama_host: str = "http://ollama:11434"
    litellm_url: str = "http://litellm:4001"
    gateway_url: str = "http://gateway:4000"
    litellm_master_key: str = ""
    langfuse_url: str = "http://langfuse-web:3000"
    langfuse_ui_url: str = "http://localhost:3100"
    guardrails_provider: str = "llm_guard"
    guard_llm_url: str = "http://guardrails:8088"
    guard_nemo_url: str = "http://nemo-guardrails:8089"

    vector_enabled: bool = False
    vector_provider: str = "qdrant"
    qdrant_url: str = "http://qdrant:6333"
    pgvector_dsn: str = ""
    embeddings_enabled: bool = True
    embeddings_model: str = "nomic-embed-text"

    def insecure_secrets(self) -> list[str]:
        """Secret settings that are empty or shipped defaults."""
        bad_values = {"", "niyan", "sk-niyan-local", "change-me-niyan-dev-secret"}

        def bad(v: str) -> bool:
            v = (v or "").strip()
            return v in bad_values or "change-me" in v.lower()

        out = []
        if bad(self.niyan_admin_password):
            out.append("NIYAN_ADMIN_PASSWORD")
        if bad(self.niyan_jwt_secret):
            out.append("NIYAN_JWT_SECRET")
        return out

    def assert_secure(self) -> None:
        bad = self.insecure_secrets()
        if bad and not self.niyan_allow_insecure_defaults:
            raise RuntimeError(
                "Refusing to start: empty or default secrets: " + ", ".join(bad)
                + ". Run ./install.sh (niyan secrets init) or set NIYAN_ALLOW_INSECURE_DEFAULTS=1 for dev only."
            )

    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.niyan_cors_origins.split(",") if o.strip()]

    def resolved_config_dsn(self) -> str:
        if self.niyan_config_dsn.strip():
            return self.niyan_config_dsn.strip()
        host = self.niyan_config_pghost.strip()
        if not host:
            return ""
        user = quote(self.niyan_config_pguser, safe="")
        password = quote(self.niyan_config_pgpassword, safe="")
        db = self.niyan_config_pgdatabase.strip() or "niyan"
        return f"postgresql://{user}:{password}@{host}:{self.niyan_config_pgport}/{db}"


settings = Settings()
