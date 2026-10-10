"""Business-friendly high-level dashboard aggregate (Langfuse usage/cost + ops)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, Query
from starlette.concurrency import run_in_threadpool

from app.auth import require_admin
from app.container import provide_orchestrator
from app.schemas.models import ModelProvider, PROPRIETARY_PROVIDERS
from app.services import config_manager, health_checker
from app.services.host_metrics import collect_resources
from app.services.langfuse_metrics import load_langfuse_traffic
from app.services.orchestrator import Orchestrator
from app.services.vector_store import get_store
from app.settings import settings

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Keep in sync with services/gateway/metrics.py — API image does not ship gateway.
_APP_ALIASES = {
    "project-xyz": "enterprise-functions",
    "project_xyz": "enterprise-functions",
}


def _canonicalize_application(application: str) -> str:
    key = (application or "").strip().lower().replace("_", "-").replace(" ", "-")
    key = key.strip("-.")
    if not key:
        return "unattributed"
    return _APP_ALIASES.get(key, key)


@router.get("/resources")
async def dashboard_resources(_: str = Depends(require_admin)) -> dict:
    """Lightweight CPU / memory / GPU snapshot for live dashboard polling."""
    return collect_resources()


@router.get("")
async def dashboard(
    _: str = Depends(require_admin),
    range: Optional[str] = Query("7d", description="Preset: 24h | 7d | 30d | 90d"),
    from_date: Optional[str] = Query(None, alias="from", description="ISO start (custom range)"),
    to_date: Optional[str] = Query(None, alias="to", description="ISO end (custom range)"),
    application: Optional[str] = Query(
        None, description="Filter usage by application/project id, or 'all'"
    ),
    orchestrator: Orchestrator = Depends(provide_orchestrator),
) -> dict:
    cfg = config_manager.load_config()
    services = await run_in_threadpool(orchestrator.list_services)
    health = await health_checker.health_aggregate()
    # Profile-optional containers (host Ollama, unused qdrant, …) are not outages.
    visible = [s for s in services if s.status != "not_created"]
    running = [s for s in visible if s.healthy]

    lf = await load_langfuse_traffic(cfg, range_key=range, from_date=from_date, to_date=to_date)
    gw = await _gateway_metrics()
    models = await _model_rows(cfg, lf, gw)
    vector = await _vector_summary(cfg)
    comparison = lf.get("comparison") or _empty_comparison(cfg)

    obs = {
        "enabled": cfg.observability.enabled,
        "provider": cfg.observability.provider,
        "reachable": bool((health.get("checks") or {}).get("langfuse")),
        "keys_configured": bool(cfg.observability.public_key and cfg.observability.secret_key),
        "ui_url": settings.langfuse_ui_url,
        "note": "Tokens and proprietary API cost are pulled from Langfuse for the selected range.",
    }

    period = lf.get("period") or {}
    today = (gw or {}).get("today") or {}
    totals = (gw or {}).get("totals") or {}
    apps = _application_rows(gw, lf.get("from"), lf.get("to"))
    functions = _period_rows((gw or {}).get("by_domain") or [], lf.get("from"), lf.get("to"))
    selected_app = _canonicalize_application((application or "all").strip() or "all")
    if selected_app in {"", "all"}:
        selected_app = "all"
    app_match: Optional[Dict[str, Any]] = None
    timeseries = lf.get("timeseries") or []
    if selected_app != "all":
        app_match = next((a for a in apps if a.get("id") == selected_app), None)
        if app_match:
            period = {
                "chat_requests": app_match.get("period_requests", 0),
                "total_tokens": app_match.get("period_total_tokens", 0),
                "cost_usd": app_match.get("period_cost_usd"),
                "label": lf.get("range") or range or "7d",
            }
            timeseries = app_match.get("daily") or []

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "range": {
            "key": lf.get("range") or range or "7d",
            "from": lf.get("from"),
            "to": lf.get("to"),
        },
        "application": {
            "selected": selected_app,
            "items": apps,
            "note": (
                "X-Niyan-Application names the product. Unlabelled traffic is Unattributed. "
                "Enterprise-Functions is the shared company bucket. Token share below is by "
                "enterprise function (the policy domain sent as model, e.g. finance)."
            ),
        },
        "enterprise_functions": {
            "items": functions,
            "note": "Policy domains sent as model (finance, research, legal, …).",
        },
        "stack": {
            "status": "healthy" if health.get("ok") else "degraded",
            "healthy_services": len(running),
            "tracked_services": len(visible),
            "checks": health.get("checks") or {},
            "services": [
                {"name": s.name, "status": s.status, "healthy": s.healthy} for s in visible
            ],
        },
        "traffic": {
            "available": lf.get("source") == "langfuse" if selected_app == "all" else True,
            "source": (
                lf.get("source") or "unavailable"
                if selected_app == "all"
                else "gateway"
            ),
            "error": lf.get("error") if selected_app == "all" else None,
            "backend": "langfuse" if selected_app == "all" else "gateway",
            "period": {
                "chat_requests": period.get("chat_requests", 0),
                "total_tokens": period.get("total_tokens", 0),
                "cost_usd": period.get("cost_usd"),
                "label": lf.get("range") or range or "7d",
            },
            "timeseries": timeseries,
            # Legacy fields for older UI — map period into today for compatibility
            "today": {
                "chat_requests": period.get("chat_requests", 0),
                "embed_requests": today.get("embed_requests", 0),
                "avg_chat_latency_ms": today.get("avg_chat_latency_ms"),
                "avg_embed_latency_ms": today.get("avg_embed_latency_ms"),
                "guardrails_blocked": today.get("guardrails_blocked", 0),
                "total_tokens": period.get("total_tokens", 0),
                "cost_usd": period.get("cost_usd"),
                "date": lf.get("range"),
            },
            "lifetime": {
                "chat_requests": totals.get("chat_requests", 0),
                "embed_requests": totals.get("embed_requests", 0),
                "avg_chat_latency_ms": totals.get("avg_chat_latency_ms"),
                "avg_embed_latency_ms": totals.get("avg_embed_latency_ms"),
                "guardrails_blocked": totals.get("guardrails_blocked", 0),
                "total_tokens": period.get("total_tokens", 0),
                "cost_usd": period.get("cost_usd"),
            },
        },
        "models": models,
        "comparison": {
            **comparison,
            "providers_configured": {
                "openai": cfg.provider_ready(ModelProvider.openai),
                "gemini": cfg.provider_ready(ModelProvider.gemini),
                "anthropic": cfg.provider_ready(ModelProvider.anthropic),
            },
        },
        "embeddings": {
            "enabled": cfg.embeddings.enabled,
            "model": cfg.embeddings.model,
            **_kind_stats(gw, "embed", cfg.embeddings.model),
        },
        "vector": vector,
        "guardrails": {
            "enabled": cfg.guardrails.enabled,
            "provider": cfg.guardrails.provider.value
            if hasattr(cfg.guardrails.provider, "value")
            else cfg.guardrails.provider,
            "today_blocked": today.get("guardrails_blocked", 0),
            "lifetime_blocked": totals.get("guardrails_blocked", 0),
        },
        "observability": obs,
        "resources": collect_resources(),
    }


async def _gateway_metrics() -> Optional[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{settings.gateway_url.rstrip('/')}/metrics",
                headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
            )
            if r.status_code >= 400:
                return None
            return r.json()
    except Exception:
        return None


async def _model_rows(
    cfg,
    lf: Dict[str, Any],
    gw: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    installed = await health_checker.ollama_tags()
    lf_by_model = {m.get("model"): m for m in (lf.get("by_model") or [])}
    gw_by_model = {(m.get("kind"), m.get("model")): m for m in (gw or {}).get("by_model") or []}
    rows = []
    for m in cfg.models:
        lf_stats = lf_by_model.get(m.id) or {}
        gw_stats = gw_by_model.get(("chat", m.id)) or {}
        is_local = m.provider == ModelProvider.ollama
        is_prop = m.provider in PROPRIETARY_PROVIDERS
        cost = lf_stats.get("cost_usd") if is_prop else None
        rows.append(
            {
                "id": m.id,
                "family": m.family,
                "provider": m.provider.value,
                "deployment": m.deployment,
                "kind": "chat",
                "enabled": m.enabled,
                "default": m.default,
                "installed": (
                    m.id in installed or m.id.split(":")[0] in installed
                    if is_local
                    else cfg.provider_ready(m.provider)
                ),
                "period_requests": lf_stats.get("requests", 0),
                "period_total_tokens": lf_stats.get("total_tokens", 0),
                "period_cost_usd": cost,
                # Compat aliases used by older UI fields
                "today_requests": lf_stats.get("requests", 0),
                "requests": lf_stats.get("requests", 0),
                "avg_latency_ms": gw_stats.get("avg_latency_ms"),
                "today_avg_latency_ms": gw_stats.get("today_avg_latency_ms"),
                "today_total_tokens": lf_stats.get("total_tokens", 0),
                "total_tokens": lf_stats.get("total_tokens", 0),
                "today_cost_usd": cost,
                "cost_usd": cost,
            }
        )
    return rows


def _empty_comparison(cfg) -> Dict[str, Any]:
    return {
        "local": {
            "requests": 0,
            "tokens": 0,
            "cost_usd": None,
            "label": "Self-hosted (Ollama)",
            "api_cost_note": "Open-source cost TBD",
        },
        "proprietary": {
            "requests": 0,
            "tokens": 0,
            "cost_usd": None,
            "openai": {"requests": 0, "tokens": 0, "cost_usd": None},
            "gemini": {"requests": 0, "tokens": 0, "cost_usd": None},
            "anthropic": {"requests": 0, "tokens": 0, "cost_usd": None},
            "label": "Proprietary (OpenAI + Gemini + Anthropic)",
        },
        "note": (
            "Tokens and proprietary API cost come from Langfuse. "
            "Open-source model cost will be added later."
        ),
        "providers_configured": {
            "openai": cfg.provider_ready(ModelProvider.openai),
            "gemini": cfg.provider_ready(ModelProvider.gemini),
            "anthropic": cfg.provider_ready(ModelProvider.anthropic),
        },
    }


def _in_range(date: str, from_iso: Optional[str], to_iso: Optional[str]) -> bool:
    if not date:
        return True
    day = date[:10]
    if from_iso and day < from_iso[:10]:
        return False
    if to_iso and day > to_iso[:10]:
        return False
    return True


def _period_rows(
    items: List[Dict[str, Any]],
    from_iso: Optional[str],
    to_iso: Optional[str],
) -> List[Dict[str, Any]]:
    rows = []
    for app in items:
        daily = [
            {
                "date": d.get("date"),
                "total_tokens": d.get("total_tokens", 0),
                "cost_usd": d.get("cost_usd", 0),
                "traces": d.get("requests", 0),
                "requests": d.get("requests", 0),
            }
            for d in (app.get("daily") or [])
            if _in_range(str(d.get("date") or ""), from_iso, to_iso)
        ]
        period_req = sum(int(d.get("requests") or 0) for d in daily)
        period_tok = sum(int(d.get("total_tokens") or 0) for d in daily)
        period_cost = sum(float(d.get("cost_usd") or 0) for d in daily)
        if not daily:
            period_req = int(app.get("requests") or 0)
            period_tok = int(app.get("total_tokens") or 0)
            period_cost = float(app.get("cost_usd") or 0)
        rows.append(
            {
                "id": app.get("id") or "unknown",
                "requests": int(app.get("requests") or 0),
                "total_tokens": int(app.get("total_tokens") or 0),
                "cost_usd": round(float(app.get("cost_usd") or 0), 6),
                "today_requests": int(app.get("today_requests") or 0),
                "today_total_tokens": int(app.get("today_total_tokens") or 0),
                "today_cost_usd": round(float(app.get("today_cost_usd") or 0), 6),
                "period_requests": period_req,
                "period_total_tokens": period_tok,
                "period_cost_usd": round(period_cost, 6),
                "daily": daily,
            }
        )
    rows.sort(key=lambda a: (-a["period_requests"], -a["requests"], a["id"]))
    return rows


def _application_rows(
    gw: Optional[Dict[str, Any]],
    from_iso: Optional[str],
    to_iso: Optional[str],
) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for app in (gw or {}).get("by_application") or []:
        daily = [
            {
                "date": d.get("date"),
                "total_tokens": d.get("total_tokens", 0),
                "cost_usd": d.get("cost_usd", 0),
                "traces": d.get("requests", 0),
                "requests": d.get("requests", 0),
            }
            for d in (app.get("daily") or [])
            if _in_range(str(d.get("date") or ""), from_iso, to_iso)
        ]
        period_req = sum(int(d.get("requests") or 0) for d in daily)
        period_tok = sum(int(d.get("total_tokens") or 0) for d in daily)
        period_cost = sum(float(d.get("cost_usd") or 0) for d in daily)
        if not daily:
            period_req = int(app.get("requests") or 0)
            period_tok = int(app.get("total_tokens") or 0)
            period_cost = float(app.get("cost_usd") or 0)
        app_id = _canonicalize_application(str(app.get("id") or "unattributed"))
        row = merged.setdefault(
            app_id,
            {
                "id": app_id,
                "requests": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
                "today_requests": 0,
                "today_total_tokens": 0,
                "today_cost_usd": 0.0,
                "period_requests": 0,
                "period_total_tokens": 0,
                "period_cost_usd": 0.0,
                "daily": [],
            },
        )
        row["requests"] += int(app.get("requests") or 0)
        row["total_tokens"] += int(app.get("total_tokens") or 0)
        row["cost_usd"] += float(app.get("cost_usd") or 0)
        row["today_requests"] += int(app.get("today_requests") or 0)
        row["today_total_tokens"] += int(app.get("today_total_tokens") or 0)
        row["today_cost_usd"] += float(app.get("today_cost_usd") or 0)
        row["period_requests"] += period_req
        row["period_total_tokens"] += period_tok
        row["period_cost_usd"] += period_cost
        row["daily"].extend(daily)

    rows = []
    for row in merged.values():
        by_day: Dict[str, Dict[str, Any]] = {}
        for d in row["daily"]:
            date = str(d.get("date") or "")
            slot = by_day.setdefault(
                date, {"date": date, "total_tokens": 0, "cost_usd": 0, "traces": 0, "requests": 0}
            )
            slot["total_tokens"] += int(d.get("total_tokens") or 0)
            slot["cost_usd"] += float(d.get("cost_usd") or 0)
            slot["traces"] += int(d.get("requests") or 0)
            slot["requests"] += int(d.get("requests") or 0)
        row["daily"] = sorted(by_day.values(), key=lambda x: x["date"])
        row["cost_usd"] = round(row["cost_usd"], 6)
        row["today_cost_usd"] = round(row["today_cost_usd"], 6)
        row["period_cost_usd"] = round(row["period_cost_usd"], 6)
        rows.append(row)
    rows.sort(key=lambda a: (-a["period_requests"], -a["requests"], a["id"]))
    return rows


def _kind_stats(traffic: Optional[Dict[str, Any]], kind: str, model: str) -> Dict[str, Any]:
    for row in (traffic or {}).get("by_model") or []:
        if row.get("kind") == kind and row.get("model") == model:
            return {
                "today_requests": row.get("today_requests", 0),
                "requests": row.get("requests", 0),
                "avg_latency_ms": row.get("avg_latency_ms"),
                "today_avg_latency_ms": row.get("today_avg_latency_ms"),
                "today_total_tokens": row.get("today_total_tokens", 0),
                "total_tokens": row.get("total_tokens", 0),
                "today_cost_usd": row.get("today_cost_usd"),
                "cost_usd": row.get("cost_usd"),
            }
    today = (traffic or {}).get("today") or {}
    totals = (traffic or {}).get("totals") or {}
    if kind == "embed":
        return {
            "today_requests": today.get("embed_requests", 0),
            "requests": totals.get("embed_requests", 0),
            "avg_latency_ms": totals.get("avg_embed_latency_ms"),
            "today_avg_latency_ms": today.get("avg_embed_latency_ms"),
            "today_total_tokens": 0,
            "total_tokens": 0,
            "today_cost_usd": None,
            "cost_usd": None,
        }
    return {
        "today_requests": 0,
        "requests": 0,
        "avg_latency_ms": None,
        "today_avg_latency_ms": None,
        "today_total_tokens": 0,
        "total_tokens": 0,
        "today_cost_usd": None,
        "cost_usd": None,
    }


async def _vector_summary(cfg) -> Dict[str, Any]:
    base = {
        "enabled": cfg.vector.enabled,
        "provider": cfg.vector.provider.value
        if hasattr(cfg.vector.provider, "value")
        else cfg.vector.provider,
        "healthy": False,
        "collections": 0,
        "total_points": 0,
        "collections_detail": [],
        "detail": "disabled",
    }
    if not cfg.vector.enabled and not settings.vector_enabled:
        return base
    try:
        store = get_store()
        health = await store.health()
        cols = await store.list_collections() if health.get("ok") else []
        total_points = sum(int(c.get("points") or 0) for c in cols)
        return {
            "enabled": True,
            "provider": health.get("provider") or base["provider"],
            "healthy": bool(health.get("ok")),
            "collections": len(cols),
            "total_points": total_points,
            "collections_detail": cols,
            "detail": health.get("detail") or "",
        }
    except Exception as exc:
        base["detail"] = str(exc)
        base["enabled"] = True
        return base
