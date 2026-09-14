"""Unit tests for loadtest SSRF guards and job building."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.schemas.loadtest import LoadTestCreate, LoadTestTarget
from app.services import loadtest_runner


def test_validate_custom_url_rejects_non_http():
    with pytest.raises(HTTPException) as ei:
        loadtest_runner.validate_custom_url("ftp://example.com/x")
    assert ei.value.status_code == 400


def test_validate_custom_url_rejects_metadata():
    with pytest.raises(HTTPException):
        loadtest_runner.validate_custom_url("http://metadata.google.internal/latest")


def test_validate_custom_url_blocks_private_by_default():
    with pytest.raises(HTTPException) as ei:
        loadtest_runner.validate_custom_url("http://127.0.0.1:8080/health")
    assert "internal" in str(ei.value.detail).lower() or "blocked" in str(ei.value.detail).lower()


def test_validate_custom_url_allows_private_when_flagged():
    url = loadtest_runner.validate_custom_url(
        "http://127.0.0.1:8080/health", allow_internal=True
    )
    assert url.startswith("http://127.0.0.1")


def test_build_job_gateway_chat_caps():
    body = LoadTestCreate(
        target_type=LoadTestTarget.gateway_chat,
        model="llama3.2:3b",
        users=50,
        duration_sec=600,
        spawn_rate=50,
    )
    job = loadtest_runner._build_job(body)
    assert job["users"] == 50
    assert job["duration_sec"] == 600
    assert job["target_type"] == "gateway_chat"
    assert job["model"] == "llama3.2:3b"


def test_build_job_domain_default_model():
    body = LoadTestCreate(target_type=LoadTestTarget.gateway_domain)
    job = loadtest_runner._build_job(body)
    assert job["model"] == "finance"
