from __future__ import annotations

from pathlib import Path

import pytest

from app.container import build_container, reset_container, set_container
from app.schemas.models import NiyanConfig
from app.services import config_manager
from app.services.config_store import (
    ConfigReadOnlyError,
    FileConfigStore,
    ReadOnlyConfigStore,
)


@pytest.fixture(autouse=True)
def _clean_container():
    reset_container()
    yield
    reset_container()


def test_save_delegates_to_writable_store(tmp_path: Path):
    set_container(build_container(config_store=FileConfigStore(tmp_path / "n.yaml", tmp_path)))
    config_manager.save_config(NiyanConfig(profile="written"))
    assert (tmp_path / "n.yaml").exists()


def test_save_on_readonly_store_raises(tmp_path: Path):
    set_container(build_container(config_store=ReadOnlyConfigStore(tmp_path / "n.yaml", tmp_path)))
    with pytest.raises(ConfigReadOnlyError):
        config_manager.save_config(NiyanConfig(profile="x"))


def test_load_on_readonly_store_does_not_write(tmp_path: Path):
    # No file on disk -> curation must NOT try to persist (writable False + no file).
    set_container(build_container(config_store=ReadOnlyConfigStore(tmp_path / "n.yaml", tmp_path)))
    cfg = config_manager.load_config()
    assert isinstance(cfg, NiyanConfig)
    assert not (tmp_path / "n.yaml").exists()


def test_readonly_load_with_existing_file_does_not_write(tmp_path, monkeypatch):
    # Seed a config file, then mount it read-only.
    path = tmp_path / "n.yaml"
    FileConfigStore(path, tmp_path).save(NiyanConfig(profile="seed"))
    before = path.read_text()
    # Make the persist guard's outer condition (settings.niyan_config_path.exists()) TRUE
    # so curation would try to persist if the inner store.writable guard were absent.
    monkeypatch.setattr(config_manager.settings, "niyan_config_path", path)
    set_container(build_container(config_store=ReadOnlyConfigStore(path, tmp_path)))
    cfg = config_manager.load_config()          # must NOT raise ConfigReadOnlyError
    assert isinstance(cfg, NiyanConfig)
    assert path.read_text() == before           # readonly store: file unchanged


def test_writable_curation_does_not_create_file_when_absent(tmp_path, monkeypatch):
    path = tmp_path / "n.yaml"                   # absent
    monkeypatch.setattr(config_manager.settings, "niyan_config_path", path)
    set_container(build_container(config_store=FileConfigStore(path, tmp_path)))
    config_manager.load_config()                 # curation runs, but file absent -> no write
    assert not path.exists()
