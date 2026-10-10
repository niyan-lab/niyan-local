from __future__ import annotations

from app.settings import Settings


def test_cors_origins_list_empty_is_empty():
    s = Settings(niyan_cors_origins="")
    assert s.cors_origins_list() == []


def test_cors_origins_list_parses_and_strips():
    s = Settings(niyan_cors_origins="http://a.test, http://b.test ,")
    assert s.cors_origins_list() == ["http://a.test", "http://b.test"]


def test_langfuse_ui_url_default_and_env(monkeypatch):
    from app.settings import Settings

    monkeypatch.delenv("LANGFUSE_UI_URL", raising=False)
    assert Settings().langfuse_ui_url == "http://localhost:3100"

    monkeypatch.setenv("LANGFUSE_UI_URL", "http://langfuse.example.com")
    assert Settings().langfuse_ui_url == "http://langfuse.example.com"


def test_resolved_config_dsn_prefers_explicit_url():
    s = Settings(niyan_config_dsn="postgresql://u:p@db:5432/niyan", niyan_config_pghost="ignored")
    assert s.resolved_config_dsn() == "postgresql://u:p@db:5432/niyan"


def test_resolved_config_dsn_builds_from_parts():
    s = Settings(
        niyan_config_dsn="",
        niyan_config_pghost="niyan-postgres",
        niyan_config_pguser="niyan",
        niyan_config_pgpassword="p@ss:word",
        niyan_config_pgdatabase="niyan",
    )
    assert s.resolved_config_dsn() == "postgresql://niyan:p%40ss%3Aword@niyan-postgres:5432/niyan"


def test_resolved_config_dsn_empty_without_host():
    s = Settings(niyan_config_dsn="", niyan_config_pghost="")
    assert s.resolved_config_dsn() == ""
