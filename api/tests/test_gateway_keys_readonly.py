"""Gateway keys are read-only in the API/UI (rotate via `niyan secrets rotate gateway-key`)."""
import asyncio

import pytest
from fastapi import HTTPException

from app.routers import gateway as gw
from app.schemas.models import NiyanConfig
from app.services.config_secrets import MASK

KEY = "sk-niyan-" + "a" * 48


@pytest.fixture
def store(monkeypatch):
    cfg = NiyanConfig()
    cfg.proxy.api_keys = [KEY]
    state = {"cfg": cfg, "saved": None}
    monkeypatch.setattr(gw.config_manager, "load_config", lambda: state["cfg"].model_copy(deep=True))

    def save(c):
        state["saved"] = c
        return c

    monkeypatch.setattr(gw.config_manager, "save_config", save)
    return state


def run(coro):
    return asyncio.run(coro)


def test_put_gateway_new_key_rejected_409(store):
    with pytest.raises(HTTPException) as e:
        run(gw.put_gateway_config(gw.GatewayUpdate(port=4000, api_keys=["sk-niyan-" + "b" * 48]), "admin"))
    assert e.value.status_code == 409 and "niyan secrets rotate gateway-key" in e.value.detail
    assert store["saved"] is None


def test_put_gateway_port_only_ok_keys_untouched(store):
    r = run(gw.put_gateway_config(gw.GatewayUpdate(port=4100), "admin"))
    assert r["ok"] and store["saved"].proxy.port == 4100 and store["saved"].proxy.api_keys == [KEY]
    # unchanged / masked echo also accepted
    run(gw.put_gateway_config(gw.GatewayUpdate(port=4000, api_keys=[KEY]), "admin"))
    run(gw.put_gateway_config(gw.GatewayUpdate(port=4000, api_keys=[MASK]), "admin"))


def test_put_config_with_changed_keys_rejected(store):
    body = NiyanConfig()
    body.proxy.api_keys = ["sk-niyan-" + "c" * 48]
    with pytest.raises(HTTPException) as e:
        run(gw.put_config(body, "admin"))
    assert e.value.status_code == 409
    body.proxy.api_keys = [MASK]  # admin UI round-trip of the masked config is fine
    run(gw.put_config(body, "admin"))
    assert store["saved"] is not None  # (the real store merges the mask back to the stored key)


def test_get_gateway_marks_read_only(store):
    r = run(gw.gateway_config("admin"))
    assert r["api_keys"] == [KEY] and r["api_keys_read_only"] is True
