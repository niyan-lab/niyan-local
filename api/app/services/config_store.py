"""Config storage seam.

Postgres is the live store on VM and Kubernetes. `niyan.yaml` is the seed and
the fallback when Postgres is unreachable. Successful saves also publish JSON
to Redis so the gateway can hot-reload without a writable ConfigMap.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable
from urllib.parse import urlparse, urlunparse

import yaml

from app.schemas.models import NiyanConfig

logger = logging.getLogger(__name__)

CONFIG_ROW_ID = "default"
CONFIG_TABLE = "niyan_runtime_config"
# Keep in sync with services/gateway/runtime_config.py
REDIS_CONFIG_JSON = "niyan:config:json"
REDIS_CONFIG_VERSION = "niyan:config:version"


class ConfigReadOnlyError(RuntimeError):
    """Raised when a write is attempted against a read-only (declarative) store."""


@runtime_checkable
class ConfigStore(Protocol):
    # True if save() persists; False if save() raises ConfigReadOnlyError.
    writable: bool

    def load(self) -> NiyanConfig: ...

    def save(self, config: NiyanConfig) -> NiyanConfig:
        """Persist config. MAY raise ConfigReadOnlyError when the store is not writable (see `writable`)."""
        ...


class FileConfigStore:
    """Read/write niyan.yaml. Used as seed, fallback, and best-effort projection."""

    writable = True

    def __init__(self, path: Path, root: Path) -> None:
        self.path = Path(path)
        self.root = Path(root)

    def load(self) -> NiyanConfig:
        if self.path.exists():
            data = yaml.safe_load(self.path.read_text()) or {}
            return NiyanConfig.model_validate(data)
        example = self.root / "configs" / "niyan.example.yaml"
        if example.exists():
            data = yaml.safe_load(example.read_text()) or {}
            return NiyanConfig.model_validate(data)
        return NiyanConfig()

    def save(self, config: NiyanConfig) -> NiyanConfig:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False))
        return config


class ReadOnlyConfigStore(FileConfigStore):
    """Legacy K8s Phase A store. Kept for tests; runtime uses DbConfigStore."""

    writable = False

    def save(self, config: NiyanConfig) -> NiyanConfig:
        raise ConfigReadOnlyError(
            "Niyan config is declarative on Kubernetes; edit Helm values and run `helm upgrade`."
        )


class DbConfigStore:
    """Postgres primary, file fallback, Redis fan-out for the gateway."""

    writable = True

    def __init__(
        self,
        dsn: str,
        file_store: FileConfigStore,
        redis_host: str = "",
        redis_port: int = 6379,
        redis_client=None,
    ) -> None:
        self.dsn = dsn
        self.file_store = file_store
        self.redis_host = redis_host
        self.redis_port = redis_port
        self._redis = redis_client
        self._redis_tried = redis_client is not None
        self._schema_ready = False

    def load(self) -> NiyanConfig:
        try:
            self.ensure_schema()
            cfg = self._load_db()
            if cfg is None:
                cfg = self.file_store.load()
                self._save_db(cfg)
            self._publish(cfg)
            return cfg
        except Exception as exc:
            logger.warning("config db unavailable (%s); using niyan.yaml fallback", exc)
            return self.file_store.load()

    def save(self, config: NiyanConfig) -> NiyanConfig:
        db_error: Optional[BaseException] = None
        try:
            self.ensure_schema()
            self._save_db(config)
        except Exception as exc:
            db_error = exc
            logger.warning("config db save failed (%s); falling back to file", exc)
        self._publish(config)
        file_error = self._try_write_file(config)
        if db_error is not None and file_error is not None:
            raise db_error
        return config

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        try:
            self._create_table()
        except Exception as exc:
            if "does not exist" not in str(exc):
                raise
            self._create_database()
            self._create_table()
        self._schema_ready = True

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self.dsn, connect_timeout=3, row_factory=dict_row)

    def _create_table(self) -> None:
        with self._connect() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {CONFIG_TABLE} (
                    id TEXT PRIMARY KEY,
                    version INT NOT NULL DEFAULT 1,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            conn.commit()

    def _create_database(self) -> None:
        import psycopg

        parsed = urlparse(self.dsn)
        dbname = (parsed.path or "/niyan").lstrip("/") or "niyan"
        admin = urlunparse(parsed._replace(path="/postgres"))
        with psycopg.connect(admin, autocommit=True, connect_timeout=3) as conn:
            exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)
            ).fetchone()
            if not exists:
                conn.execute(f'CREATE DATABASE "{dbname}"')

    def _load_db(self) -> Optional[NiyanConfig]:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT payload FROM {CONFIG_TABLE} WHERE id = %s",
                (CONFIG_ROW_ID,),
            ).fetchone()
        if not row or row.get("payload") is None:
            return None
        return NiyanConfig.model_validate(row["payload"])

    def _save_db(self, config: NiyanConfig) -> None:
        from psycopg.types.json import Jsonb

        payload = Jsonb(config.model_dump(mode="json"))
        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {CONFIG_TABLE} (id, version, payload, updated_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (id) DO UPDATE SET
                    version = EXCLUDED.version,
                    payload = EXCLUDED.payload,
                    updated_at = now()
                """,
                (CONFIG_ROW_ID, config.version, payload),
            )
            conn.commit()

    def _redis_client(self):
        if self._redis_tried:
            return self._redis
        self._redis_tried = True
        if not self.redis_host:
            self._redis = None
            return None
        try:
            import redis

            client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                decode_responses=True,
                socket_connect_timeout=0.5,
            )
            client.ping()
            self._redis = client
        except Exception as exc:
            logger.warning("config redis unavailable (%s); gateway will use file fallback", exc)
            self._redis = None
        return self._redis

    def _publish(self, config: NiyanConfig) -> None:
        client = self._redis_client()
        if client is None:
            return
        try:
            client.set(REDIS_CONFIG_JSON, json.dumps(config.model_dump(mode="json")))
            client.set(REDIS_CONFIG_VERSION, str(time.time_ns()))
        except Exception as exc:
            logger.warning("config redis publish failed: %s", exc)

    def _try_write_file(self, config: NiyanConfig) -> Optional[BaseException]:
        try:
            self.file_store.save(config)
            return None
        except OSError as exc:
            logger.info("config file projection skipped: %s", exc)
            return exc


def build_config_store(settings) -> ConfigStore:
    file_store = FileConfigStore(settings.niyan_config_path, settings.niyan_root)
    dsn = settings.resolved_config_dsn()
    if not dsn:
        return file_store
    return DbConfigStore(
        dsn=dsn,
        file_store=file_store,
        redis_host=settings.redis_host,
        redis_port=settings.redis_port,
    )
