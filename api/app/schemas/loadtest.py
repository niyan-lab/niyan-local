"""Load test request/response schemas."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class LoadTestTarget(str, Enum):
    gateway_chat = "gateway_chat"
    gateway_embeddings = "gateway_embeddings"
    gateway_domain = "gateway_domain"
    custom = "custom"


class LoadTestStatus(str, Enum):
    queued = "queued"
    running = "running"
    finished = "finished"
    failed = "failed"
    stopped = "stopped"


class LoadTestCreate(BaseModel):
    target_type: LoadTestTarget = LoadTestTarget.gateway_chat
    # Gateway presets
    model: Optional[str] = Field(
        default=None,
        description="Model id or domain id (for gateway_domain)",
    )
    messages: Optional[List[Dict[str, str]]] = None
    input: Optional[str] = Field(default=None, description="Embeddings input text")
    # Custom endpoint
    url: Optional[str] = None
    method: Optional[str] = "POST"
    headers: Optional[Dict[str, str]] = None
    body: Optional[Any] = None
    allow_internal_urls: bool = False
    # Auth + load params
    auth_bearer: Optional[str] = None
    host: Optional[str] = None
    users: int = Field(default=5, ge=1, le=50)
    spawn_rate: float = Field(default=1.0, gt=0, le=50)
    duration_sec: int = Field(default=30, ge=5, le=600)
    name: Optional[str] = None


class LoadTestProgress(BaseModel):
    updated_at: Optional[str] = None
    elapsed_sec: float = 0
    users: int = 0
    requests: int = 0
    failures: int = 0
    fail_percent: float = 0
    rps: float = 0
    latency_ms: Dict[str, float] = Field(default_factory=dict)
    total_tokens: int = 0


class LoadTestSummary(BaseModel):
    requests: int = 0
    failures: int = 0
    fail_percent: float = 0
    rps: float = 0
    latency_ms: Dict[str, float] = Field(default_factory=dict)
    total_tokens: int = 0
    duration_sec: float = 0


class LoadTestRun(BaseModel):
    id: str
    name: Optional[str] = None
    status: LoadTestStatus
    target_type: LoadTestTarget
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    job: Dict[str, Any] = Field(default_factory=dict)
    progress: Optional[LoadTestProgress] = None
    summary: Optional[LoadTestSummary] = None
    cost_warning: Optional[str] = None
    artifacts: Dict[str, bool] = Field(default_factory=dict)
