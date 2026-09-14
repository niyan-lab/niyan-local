"""LLM Guard-compatible HTTP sidecar (regex PII + injection / toxicity / secrets)."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Set

from fastapi import FastAPI
from pydantic import BaseModel

INPUT_SCANNERS = {
    s.strip()
    for s in os.getenv("SCANNERS", os.getenv("INPUT_SCANNERS", "prompt_injection,pii")).split(",")
    if s.strip()
}
OUTPUT_SCANNERS = {
    s.strip()
    for s in os.getenv("OUTPUT_SCANNERS", "pii,toxicity,secrets").split(",")
    if s.strip()
}
ON_FAILURE = os.getenv("ON_FAILURE", "allow")

app = FastAPI(title="Niyan LLM Guard", version="0.1.0")

PII_PATTERNS = [
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN_REDACTED]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[EMAIL_REDACTED]"),
    (re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b"), "[PHONE_REDACTED]"),
]

SECRET_PATTERNS = [
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "[API_KEY_REDACTED]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[AWS_KEY_REDACTED]"),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "[PRIVATE_KEY_REDACTED]"),
    (re.compile(r"\b(?:ghp|gho|github_pat)_[A-Za-z0-9_]{20,}\b"), "[GITHUB_TOKEN_REDACTED]"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "[SLACK_TOKEN_REDACTED]"),
]

INJECTION_MARKERS = [
    "ignore previous instructions",
    "ignore all previous",
    "system prompt",
    "jailbreak",
    "dan mode",
]

TOXICITY_MARKERS = [
    "kill yourself",
    "you should die",
    "i hate you",
]


class CheckRequest(BaseModel):
    stage: str = "input"
    text: str


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "provider": "llm_guard",
        "input_scanners": sorted(INPUT_SCANNERS),
        "output_scanners": sorted(OUTPUT_SCANNERS),
    }


def _scanners_for(stage: str) -> Set[str]:
    if (stage or "input").lower() == "output":
        return OUTPUT_SCANNERS
    return INPUT_SCANNERS


@app.post("/check")
def check(body: CheckRequest) -> Dict[str, Any]:
    text = body.text or ""
    stage = (body.stage or "input").lower()
    scanners = _scanners_for(stage)
    reasons: List[str] = []
    redacted = text

    if "prompt_injection" in scanners:
        lower = text.lower()
        for marker in INJECTION_MARKERS:
            if marker in lower:
                reasons.append(f"prompt_injection:{marker}")
                break

    if "toxicity" in scanners:
        lower = text.lower()
        for marker in TOXICITY_MARKERS:
            if marker in lower:
                reasons.append(f"toxicity:{marker}")
                break

    if "pii" in scanners:
        for pattern, repl in PII_PATTERNS:
            if pattern.search(redacted):
                reasons.append("pii_detected")
                redacted = pattern.sub(repl, redacted)

    if "secrets" in scanners:
        for pattern, repl in SECRET_PATTERNS:
            if pattern.search(redacted):
                reasons.append("secrets_detected")
                redacted = pattern.sub(repl, redacted)

    hard_block = any(
        r.startswith("prompt_injection") or r.startswith("toxicity") for r in reasons
    )
    if hard_block:
        return {
            "allowed": False,
            "stage": stage,
            "reason": "; ".join(reasons),
            "provider": "llm_guard",
            "scanners": sorted(scanners),
        }

    return {
        "allowed": True,
        "stage": stage,
        "reason": "; ".join(reasons) if reasons else "ok",
        "text": redacted if redacted != text else text,
        "provider": "llm_guard",
        "scanners": sorted(scanners),
    }
