"""Enterprise AI Policy: resolve domain id → concrete model."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class ResolveResult:
    def __init__(
        self,
        *,
        requested: str,
        resolved_model: str,
        domain: Optional[str] = None,
        deployment: Optional[str] = None,
        via_policy: bool = False,
        error: Optional[str] = None,
    ) -> None:
        self.requested = requested
        self.resolved_model = resolved_model
        self.domain = domain
        self.deployment = deployment
        self.via_policy = via_policy
        self.error = error

    @property
    def ok(self) -> bool:
        return not self.error


def resolve_model(requested: str, policy: Optional[Dict[str, Any]]) -> ResolveResult:
    """Map a request `model` field through enterprise_policy when it matches a domain.

    Domain match is case-insensitive. When policy is disabled / missing / no match,
    the requested id is passed through unchanged (real model ids keep working).
    """
    req = (requested or "").strip()
    if not req:
        return ResolveResult(requested=requested or "", resolved_model="", error="model is required")

    if not policy or not policy.get("enabled", True):
        return ResolveResult(requested=req, resolved_model=req)

    domains: List[Dict[str, Any]] = list(policy.get("domains") or [])
    key = req.lower()
    match: Optional[Dict[str, Any]] = None
    for d in domains:
        if str(d.get("id") or "").strip().lower() == key:
            match = d
            break

    if match is None:
        return ResolveResult(requested=req, resolved_model=req)

    if not match.get("enabled", True):
        return ResolveResult(
            requested=req,
            resolved_model="",
            domain=str(match.get("id") or req),
            error=f"domain '{match.get('id')}' is disabled in enterprise policy",
        )

    deployment = str(match.get("deployment") or "local").strip().lower()
    if deployment not in {"local", "proprietary"}:
        deployment = "local"

    if deployment == "proprietary":
        target = str(match.get("proprietary_model") or "").strip()
        kind = "proprietary_model"
    else:
        target = str(match.get("local_model") or "").strip()
        kind = "local_model"

    if not target:
        return ResolveResult(
            requested=req,
            resolved_model="",
            domain=str(match.get("id") or req),
            deployment=deployment,
            via_policy=True,
            error=f"domain '{match.get('id')}' has empty {kind}",
        )

    return ResolveResult(
        requested=req,
        resolved_model=target,
        domain=str(match.get("id") or req).lower(),
        deployment=deployment,
        via_policy=True,
    )
