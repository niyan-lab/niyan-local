from __future__ import annotations

from pathlib import Path

import pytest

from app.schemas.models import NiyanConfig
from app.services.config_store import (
    REDIS_CONFIG_JSON,
    REDIS_CONFIG_VERSION,
    ConfigReadOnlyError,
    DbConfigStore,
    FileConfigStore,
    ReadOnlyConfigStore,
)


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def set(self, key: str, value: str) -> None:
        self.data[key] = value

    def get(self, key: str):
        return self.data.get(key)

    def ping(self) -> bool:
        return True


class HarnessStore(DbConfigStore):
    def __init__(self, file_store: FileConfigStore, *, db_down: bool = False) -> None:
        super().__init__(
            dsn="postgresql://unused",
            file_store=file_store,
            redis_client=FakeRedis(),
        )
        self._row = None
        self.db_down = db_down
        self._schema_ready = True

    def ensure_schema(self) -> None:
        if self.db_down:
            raise RuntimeError("db down")

    def _load_db(self):
        if self.db_down:
            raise RuntimeError("db down")
        if self._row is None:
            return None
        return NiyanConfig.model_validate(self._row)

    def _save_db(self, config: NiyanConfig) -> None:
        if self.db_down:
            raise RuntimeError("db down")
        self._row = config.model_dump(mode="json")


def test_file_store_load_defaults_when_missing(tmp_path: Path):
    store = FileConfigStore(path=tmp_path / "niyan.yaml", root=tmp_path)
    cfg = store.load()
    assert isinstance(cfg, NiyanConfig)


def test_file_store_save_then_load_roundtrip(tmp_path: Path):
    store = FileConfigStore(path=tmp_path / "niyan.yaml", root=tmp_path)
    cfg = NiyanConfig(profile="roundtrip")
    store.save(cfg)
    assert (tmp_path / "niyan.yaml").exists()
    assert store.load().profile == "roundtrip"


def test_readonly_store_writable_false_and_save_raises(tmp_path: Path):
    path = tmp_path / "niyan.yaml"
    FileConfigStore(path=path, root=tmp_path).save(NiyanConfig(profile="seed"))
    ro = ReadOnlyConfigStore(path=path, root=tmp_path)
    assert ro.writable is False
    assert ro.load().profile == "seed"  # still reads the mounted file
    with pytest.raises(ConfigReadOnlyError):
        ro.save(NiyanConfig(profile="nope"))


def test_db_store_seeds_from_file_and_publishes_redis(tmp_path: Path):
    path = tmp_path / "niyan.yaml"
    FileConfigStore(path, tmp_path).save(NiyanConfig(profile="from-file"))
    store = HarnessStore(FileConfigStore(path, tmp_path))
    cfg = store.load()
    assert cfg.profile == "from-file"
    assert store._row is not None
    assert '"from-file"' in store._redis.data[REDIS_CONFIG_JSON]
    assert REDIS_CONFIG_VERSION in store._redis.data


def test_db_store_prefers_db_over_file(tmp_path: Path):
    path = tmp_path / "niyan.yaml"
    file_store = FileConfigStore(path, tmp_path)
    file_store.save(NiyanConfig(profile="file"))
    store = HarnessStore(file_store)
    store.save(NiyanConfig(profile="db"))
    file_store.save(NiyanConfig(profile="stale-file"))
    assert store.load().profile == "db"


def test_db_store_load_falls_back_to_file_when_db_down(tmp_path: Path):
    path = tmp_path / "niyan.yaml"
    FileConfigStore(path, tmp_path).save(NiyanConfig(profile="fallback"))
    store = HarnessStore(FileConfigStore(path, tmp_path), db_down=True)
    assert store.load().profile == "fallback"


def test_db_store_save_falls_back_to_file_when_db_down(tmp_path: Path):
    path = tmp_path / "niyan.yaml"
    store = HarnessStore(FileConfigStore(path, tmp_path), db_down=True)
    store.save(NiyanConfig(profile="file-write"))
    assert FileConfigStore(path, tmp_path).load().profile == "file-write"


def test_db_store_save_succeeds_when_file_is_readonly(tmp_path: Path):
    path = tmp_path / "niyan.yaml"

    class ReadOnlyFile(FileConfigStore):
        def save(self, config: NiyanConfig) -> NiyanConfig:
            raise OSError("Read-only file system")

    store = HarnessStore(ReadOnlyFile(path, tmp_path))
    saved = store.save(NiyanConfig(profile="db-only"))
    assert saved.profile == "db-only"
    assert store.load().profile == "db-only"


def test_db_store_save_raises_when_db_and_file_fail(tmp_path: Path):
    class ReadOnlyFile(FileConfigStore):
        def save(self, config: NiyanConfig) -> NiyanConfig:
            raise OSError("Read-only file system")

    store = HarnessStore(ReadOnlyFile(tmp_path / "niyan.yaml", tmp_path), db_down=True)
    with pytest.raises(RuntimeError, match="db down"):
        store.save(NiyanConfig(profile="nowhere"))


def test_b1_legacy_db_defaults_do_not_override_yaml_secrets(tmp_path: Path):
    """Old DB row with shipped defaults + new yaml secrets -> yaml wins, saves can't reintroduce defaults."""
    import json as _json

    path = tmp_path / "niyan.yaml"
    gen = {"admin_auth": {"username": "admin", "password": "Gen-erated-pass-123456", "jwt_secret": "j" * 64},
           "proxy": {"api_keys": ["sk-niyan-" + "a" * 48]}}
    FileConfigStore(path=path, root=tmp_path).save(NiyanConfig.model_validate(gen))
    store = HarnessStore(FileConfigStore(path=path, root=tmp_path))
    store._row = NiyanConfig.model_validate(
        {"admin_auth": {"username": "admin", "password": "niyan", "jwt_secret": "change-me-niyan-dev-secret"},
         "proxy": {"api_keys": ["sk-niyan-local"]}, "profile": "from-db"}
    ).model_dump(mode="json")
    cfg = store.load()
    assert cfg.admin_auth.password == "Gen-erated-pass-123456"
    assert cfg.admin_auth.jwt_secret == "j" * 64
    assert cfg.proxy.api_keys == ["sk-niyan-" + "a" * 48]
    # Admin UI save that round-trips old/masked values
    incoming = cfg.model_copy(deep=True)
    incoming.admin_auth.password = "niyan"
    incoming.admin_auth.jwt_secret = "********"
    incoming.proxy.api_keys = ["sk-niyan-local"]
    store.save(incoming)
    on_disk = FileConfigStore(path=path, root=tmp_path).load()
    assert on_disk.admin_auth.password == "Gen-erated-pass-123456"
    assert on_disk.proxy.api_keys == ["sk-niyan-" + "a" * 48]
    payload = store._redis.data.get(REDIS_CONFIG_JSON)
    assert payload
    assert "Gen-erated-pass" not in payload and "sk-niyan-aaaa" not in payload and "j" * 64 not in payload
