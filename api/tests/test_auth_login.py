"""POST /api/auth/login: rate limit, insecure-password 503, XFF trust."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import login_limiter as ll
from app.routers import auth
from app.settings import settings

GOOD = "S3cure-" + "p" * 24


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "niyan_admin_username", "admin")
    monkeypatch.setattr(settings, "niyan_admin_password", GOOD)
    monkeypatch.setattr(settings, "niyan_jwt_secret", "j" * 64, raising=False)
    monkeypatch.delenv("NIYAN_TRUSTED_PROXIES", raising=False)
    ll.limiter.clear()
    app = FastAPI()
    app.include_router(auth.router)
    yield TestClient(app)
    ll.limiter.clear()


def login(c, pw, user="admin", headers=None):
    return c.post("/api/auth/login", json={"username": user, "password": pw}, headers=headers or {})


def test_good_and_bad_credentials(client):
    assert login(client, GOOD).status_code == 200
    assert "access_token" in login(client, GOOD).json()
    r = login(client, "wrong")
    assert r.status_code == 401 and r.json()["detail"] == "Invalid credentials"


def test_sixth_failure_is_429_with_retry_after(client):
    for _ in range(5):
        assert login(client, "wrong").status_code == 401
    r = login(client, "wrong")
    assert r.status_code == 429
    assert 1 <= int(r.headers["Retry-After"]) <= 60
    # Locked even with the right password until the window passes.
    assert login(client, GOOD).status_code == 429
    # Other usernames are a separate bucket.
    assert login(client, "wrong", user="other").status_code == 401


def test_success_resets_counter(client):
    for _ in range(4):
        login(client, "wrong")
    assert login(client, GOOD).status_code == 200
    for _ in range(5):
        assert login(client, "wrong").status_code == 401
    assert login(client, "wrong").status_code == 429


def test_sliding_window_expires():
    now = [0.0]
    lim = ll.LoginLimiter(max_failures=5, window=60, clock=lambda: now[0])
    for i in range(5):
        now[0] = i
        lim.record_failure("1.2.3.4", "admin")
    assert lim.retry_after("1.2.3.4", "admin") == 56
    now[0] = 60.5  # first failure (t=0) left the window
    assert lim.retry_after("1.2.3.4", "admin") == 0


@pytest.mark.parametrize("pw", ["", "niyan", "change-me", "__SET_ME__"])
def test_insecure_configured_password_is_503(client, monkeypatch, pw):
    monkeypatch.setattr(settings, "niyan_admin_password", pw)
    r = login(client, pw)
    assert r.status_code == 503
    assert r.json() == {"detail": auth.NOT_CONFIGURED}  # config state only, no secret echoed
    assert "niyan secrets init" in r.json()["detail"]


def test_xff_ignored_from_untrusted_peer():
    assert ll.client_ip("10.0.0.5", "9.9.9.9", trusted="") == "10.0.0.5"
    assert ll.client_ip("10.0.0.5", "9.9.9.9", trusted="192.168.0.0/16") == "10.0.0.5"


def test_xff_used_from_trusted_proxy_rightmost_hop():
    assert ll.client_ip("172.18.0.3", "6.6.6.6, 9.9.9.9", trusted="172.16.0.0/12") == "9.9.9.9"
    assert ll.client_ip("172.18.0.3", None, trusted="172.16.0.0/12") == "172.18.0.3"


def test_spoofed_xff_does_not_bypass_limit(client):
    for i in range(5):
        login(client, "wrong", headers={"X-Forwarded-For": f"8.8.8.{i}"})
    assert login(client, "wrong", headers={"X-Forwarded-For": "8.8.8.99"}).status_code == 429
