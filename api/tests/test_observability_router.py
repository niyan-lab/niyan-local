from __future__ import annotations

from app.routers import observability


class _Obs:
    enabled = True
    provider = "langfuse"
    host = "http://niyan-langfuse-web:3000"
    public_key = "pk-1234"
    secret_key = "sk-abcd"


class _Cfg:
    observability = _Obs()


def test_status_payload_ui_url_is_settings_driven(monkeypatch):
    monkeypatch.setattr(observability.settings, "langfuse_ui_url", "http://langfuse.local:3000")
    payload = observability._status_payload(_Cfg())
    assert payload["ui_url"] == "http://langfuse.local:3000"
