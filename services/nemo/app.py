"""NeMo Guardrails-style policy HTTP sidecar (prototype)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

import yaml
from fastapi import FastAPI
from pydantic import BaseModel

CONFIG_PATH = Path(os.getenv("CONFIG_PATH", "/config/config.yml"))
ON_FAILURE = os.getenv("ON_FAILURE", "allow")

app = FastAPI(title="Niyan NeMo Guardrails", version="0.1.0")


def _load_policies() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        return yaml.safe_load(CONFIG_PATH.read_text()) or {}
    return {
        "policies": {
            "banned_topics": ["how to build a bomb", "credit card fraud"],
            "output_banned": ["kill yourself"],
            "block_message": "I cannot help with that request under Niyan NeMo policy.",
        }
    }


class CheckRequest(BaseModel):
    stage: str = "input"
    text: str


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "provider": "nemo"}


@app.post("/check")
def check(body: CheckRequest) -> Dict[str, Any]:
    cfg = _load_policies()
    policies = cfg.get("policies", {})
    stage = (body.stage or "input").lower()
    text = (body.text or "").lower()
    banned_key = "output_banned" if stage == "output" else "banned_topics"
    banned: List[str] = [b.lower() for b in policies.get(banned_key, [])]
    if stage == "output" and not banned:
        banned = [b.lower() for b in policies.get("banned_topics", [])]
    for topic in banned:
        if topic and topic in text:
            return {
                "allowed": False,
                "stage": stage,
                "reason": f"nemo_policy_blocked:{topic}",
                "provider": "nemo",
                "message": policies.get("block_message", "blocked"),
            }
    return {
        "allowed": True,
        "stage": stage,
        "reason": "ok",
        "provider": "nemo",
        "text": body.text,
    }
