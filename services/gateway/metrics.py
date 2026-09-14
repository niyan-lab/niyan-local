"""Lightweight request metrics for the Niyan gateway (Redis with in-memory fallback)."""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
PREFIX = "niyan:gw:metrics"

_lock = threading.Lock()
_mem: Dict[str, float] = defaultdict(float)
_started_at = datetime.now(timezone.utc).isoformat()
_redis = None
_redis_tried = False


def _client():
    global _redis, _redis_tried
    if _redis_tried:
        return _redis
    _redis_tried = True
    try:
        import redis  # type: ignore

        c = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True, socket_connect_timeout=0.5)
        c.ping()
        _redis = c
    except Exception:
        _redis = None
    return _redis


def _day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _safe_model(model: str) -> str:
    return (model or "unknown").replace(" ", "_").replace(":", "__")


def _display_model(safe: str) -> str:
    return safe.replace("__", ":")


# Historical curl samples used `project-xyz`. New traffic and the dashboard
# always store/show that bucket as enterprise-functions.
_APP_ALIASES = {
    "project-xyz": "enterprise-functions",
    "project_xyz": "enterprise-functions",
}


def canonicalize_application(application: str) -> str:
    """Stable project id for metrics keys, Langfuse tags, and the dashboard."""
    key = (application or "").strip().lower().replace("_", "-").replace(" ", "-")
    key = key.strip("-.")
    if not key:
        return "unattributed"
    return _APP_ALIASES.get(key, key)


def _key(kind: str, model: str, field: str, day: Optional[str] = None) -> str:
    model = _safe_model(model)
    if day:
        return f"{PREFIX}:{kind}:{model}:day:{day}:{field}"
    return f"{PREFIX}:{kind}:{model}:{field}"


def _provider_key(provider: str, field: str, day: Optional[str] = None) -> str:
    provider = (provider or "unknown").replace(" ", "_")
    if day:
        return f"{PREFIX}:provider:{provider}:day:{day}:{field}"
    return f"{PREFIX}:provider:{provider}:{field}"


def _app_key(application: str, field: str, day: Optional[str] = None) -> str:
    application = _safe_model(canonicalize_application(application))
    if day:
        return f"{PREFIX}:app:{application}:day:{day}:{field}"
    return f"{PREFIX}:app:{application}:{field}"


def canonicalize_domain(domain: Optional[str]) -> str:
    """Enterprise-policy domain id (finance, research, …). Empty if the client
    called a concrete model instead of a function."""
    key = (domain or "").strip().lower().replace("_", "-").replace(" ", "-")
    return key.strip("-.")


def _domain_key(domain: str, field: str, day: Optional[str] = None) -> str:
    domain = _safe_model(canonicalize_domain(domain))
    if day:
        return f"{PREFIX}:domain:{domain}:day:{day}:{field}"
    return f"{PREFIX}:domain:{domain}:{field}"


def record(
    kind: str,
    model: str,
    latency_ms: float,
    *,
    error: bool = False,
    blocked: bool = False,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    cost_usd: float = 0.0,
    provider: str = "ollama",
    application: str = "unattributed",
    domain: Optional[str] = None,
) -> None:
    """Record one chat/embed request. kind is 'chat' or 'embed'."""
    kind = "embed" if kind == "embed" else "chat"
    model = model or "unknown"
    provider = provider or "ollama"
    application = canonicalize_application(application)
    day = _day()
    latency_ms = max(0.0, float(latency_ms))
    prompt_tokens = max(0, int(prompt_tokens))
    completion_tokens = max(0, int(completion_tokens))
    total_tokens = max(0, int(total_tokens or (prompt_tokens + completion_tokens)))
    cost_usd = max(0.0, float(cost_usd))

    keys = [
        (_key(kind, model, "count"), 1.0),
        (_key(kind, model, "lat_sum"), latency_ms),
        (_key(kind, model, "count", day), 1.0),
        (_key(kind, model, "lat_sum", day), latency_ms),
        (_key(kind, model, "tok_in"), float(prompt_tokens)),
        (_key(kind, model, "tok_out"), float(completion_tokens)),
        (_key(kind, model, "tok_total"), float(total_tokens)),
        (_key(kind, model, "cost_sum"), cost_usd),
        (_key(kind, model, "tok_in", day), float(prompt_tokens)),
        (_key(kind, model, "tok_out", day), float(completion_tokens)),
        (_key(kind, model, "tok_total", day), float(total_tokens)),
        (_key(kind, model, "cost_sum", day), cost_usd),
        (_provider_key(provider, "count"), 1.0),
        (_provider_key(provider, "tok_total"), float(total_tokens)),
        (_provider_key(provider, "cost_sum"), cost_usd),
        (_provider_key(provider, "count", day), 1.0),
        (_provider_key(provider, "tok_total", day), float(total_tokens)),
        (_provider_key(provider, "cost_sum", day), cost_usd),
        (_app_key(application, "count"), 1.0),
        (_app_key(application, "tok_total"), float(total_tokens)),
        (_app_key(application, "cost_sum"), cost_usd),
        (_app_key(application, "count", day), 1.0),
        (_app_key(application, "tok_total", day), float(total_tokens)),
        (_app_key(application, "cost_sum", day), cost_usd),
    ]
    domain = canonicalize_domain(domain)
    if domain:
        keys.extend(
            [
                (_domain_key(domain, "count"), 1.0),
                (_domain_key(domain, "tok_total"), float(total_tokens)),
                (_domain_key(domain, "cost_sum"), cost_usd),
                (_domain_key(domain, "count", day), 1.0),
                (_domain_key(domain, "tok_total", day), float(total_tokens)),
                (_domain_key(domain, "cost_sum", day), cost_usd),
            ]
        )
    if error:
        keys.append((_key(kind, model, "errors"), 1.0))
        keys.append((_key(kind, model, "errors", day), 1.0))
    if blocked:
        keys.append((_key(kind, model, "blocked"), 1.0))
        keys.append((_key(kind, model, "blocked", day), 1.0))
        keys.append((f"{PREFIX}:guardrails:blocked", 1.0))
        keys.append((f"{PREFIX}:guardrails:day:{day}:blocked", 1.0))

    r = _client()
    if r is not None:
        try:
            pipe = r.pipeline()
            for k, v in keys:
                pipe.incrbyfloat(k, v)
                pipe.expire(k, 60 * 60 * 24 * 40)  # ~40 days
            pipe.execute()
            return
        except Exception:
            pass

    with _lock:
        for k, v in keys:
            _mem[k] += v


def _scan_keys(pattern: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    r = _client()
    if r is not None:
        try:
            for k in r.scan_iter(match=pattern, count=200):
                try:
                    out[k] = float(r.get(k) or 0)
                except Exception:
                    continue
            return out
        except Exception:
            pass
    with _lock:
        for k, v in _mem.items():
            if pattern.endswith("*"):
                if k.startswith(pattern[:-1]):
                    out[k] = float(v)
            elif k == pattern:
                out[k] = float(v)
    return out


def _empty_model_entry(kind: str, model: str) -> Dict[str, Any]:
    return {
        "kind": kind,
        "model": model,
        "requests": 0,
        "errors": 0,
        "blocked": 0,
        "latency_sum_ms": 0.0,
        "today_requests": 0,
        "today_latency_sum_ms": 0.0,
        "today_errors": 0,
        "today_blocked": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "today_prompt_tokens": 0,
        "today_completion_tokens": 0,
        "today_total_tokens": 0,
        "today_cost_usd": 0.0,
    }


def _serialize_named(store: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        [
            {
                "id": e["id"],
                "requests": e["requests"],
                "total_tokens": e["total_tokens"],
                "cost_usd": round(e["cost_usd"], 6),
                "today_requests": e["today_requests"],
                "today_total_tokens": e["today_total_tokens"],
                "today_cost_usd": round(e["today_cost_usd"], 6),
                "daily": sorted(
                    [
                        {
                            "date": d["date"],
                            "requests": d["requests"],
                            "total_tokens": d["total_tokens"],
                            "cost_usd": round(d["cost_usd"], 6),
                        }
                        for d in e["daily"].values()
                    ],
                    key=lambda x: x["date"],
                ),
            }
            for e in store.values()
        ],
        key=lambda a: (-a["today_requests"], -a["requests"], a["id"]),
    )


def snapshot() -> Dict[str, Any]:
    """Aggregate metrics for the admin dashboard."""
    day = _day()
    all_keys = _scan_keys(f"{PREFIX}:*")
    by_model: Dict[str, Dict[str, Any]] = {}
    by_provider: Dict[str, Dict[str, Any]] = {}
    by_application: Dict[str, Dict[str, Any]] = {}
    by_domain: Dict[str, Dict[str, Any]] = {}
    blocked_total = 0
    blocked_today = 0

    for key, value in all_keys.items():
        rest = key[len(PREFIX) + 1 :]
        if rest == "guardrails:blocked":
            blocked_total += int(value)
            continue
        if rest.startswith("guardrails:day:") and rest.endswith(":blocked"):
            parts = rest.split(":")
            if len(parts) >= 4 and parts[2] == day:
                blocked_today += int(value)
            continue

        if rest.startswith("provider:"):
            bits = rest.split(":")
            # provider:{name}:field OR provider:{name}:day:{day}:field
            if len(bits) < 3:
                continue
            prov = bits[1]
            entry = by_provider.setdefault(
                prov,
                {
                    "provider": prov,
                    "requests": 0,
                    "total_tokens": 0,
                    "cost_usd": 0.0,
                    "today_requests": 0,
                    "today_total_tokens": 0,
                    "today_cost_usd": 0.0,
                },
            )
            if bits[2] == "day" and len(bits) >= 5:
                if bits[3] != day:
                    continue
                field = bits[4]
                if field == "count":
                    entry["today_requests"] += int(value)
                elif field == "tok_total":
                    entry["today_total_tokens"] += int(value)
                elif field == "cost_sum":
                    entry["today_cost_usd"] += float(value)
            else:
                field = bits[2]
                if field == "count":
                    entry["requests"] += int(value)
                elif field == "tok_total":
                    entry["total_tokens"] += int(value)
                elif field == "cost_sum":
                    entry["cost_usd"] += float(value)
            continue

        if rest.startswith("app:"):
            bits = rest.split(":")
            # app:{name}:field OR app:{name}:day:{day}:field
            if len(bits) < 3:
                continue
            app_id = canonicalize_application(_display_model(bits[1]))
            entry = by_application.setdefault(
                app_id,
                {
                    "id": app_id,
                    "requests": 0,
                    "total_tokens": 0,
                    "cost_usd": 0.0,
                    "today_requests": 0,
                    "today_total_tokens": 0,
                    "today_cost_usd": 0.0,
                    "daily": {},
                },
            )
            if bits[2] == "day" and len(bits) >= 5:
                date = bits[3]
                field = bits[4]
                daily = entry["daily"].setdefault(
                    date, {"date": date, "requests": 0, "total_tokens": 0, "cost_usd": 0.0}
                )
                if field == "count":
                    daily["requests"] += int(value)
                    if date == day:
                        entry["today_requests"] += int(value)
                elif field == "tok_total":
                    daily["total_tokens"] += int(value)
                    if date == day:
                        entry["today_total_tokens"] += int(value)
                elif field == "cost_sum":
                    daily["cost_usd"] += float(value)
                    if date == day:
                        entry["today_cost_usd"] += float(value)
            else:
                field = bits[2]
                if field == "count":
                    entry["requests"] += int(value)
                elif field == "tok_total":
                    entry["total_tokens"] += int(value)
                elif field == "cost_sum":
                    entry["cost_usd"] += float(value)
            continue

        if rest.startswith("domain:"):
            bits = rest.split(":")
            if len(bits) < 3:
                continue
            domain_id = canonicalize_domain(_display_model(bits[1]))
            if not domain_id:
                continue
            entry = by_domain.setdefault(
                domain_id,
                {
                    "id": domain_id,
                    "requests": 0,
                    "total_tokens": 0,
                    "cost_usd": 0.0,
                    "today_requests": 0,
                    "today_total_tokens": 0,
                    "today_cost_usd": 0.0,
                    "daily": {},
                },
            )
            if bits[2] == "day" and len(bits) >= 5:
                date = bits[3]
                field = bits[4]
                daily = entry["daily"].setdefault(
                    date, {"date": date, "requests": 0, "total_tokens": 0, "cost_usd": 0.0}
                )
                if field == "count":
                    daily["requests"] += int(value)
                    if date == day:
                        entry["today_requests"] += int(value)
                elif field == "tok_total":
                    daily["total_tokens"] += int(value)
                    if date == day:
                        entry["today_total_tokens"] += int(value)
                elif field == "cost_sum":
                    daily["cost_usd"] += float(value)
                    if date == day:
                        entry["today_cost_usd"] += float(value)
            else:
                field = bits[2]
                if field == "count":
                    entry["requests"] += int(value)
                elif field == "tok_total":
                    entry["total_tokens"] += int(value)
                elif field == "cost_sum":
                    entry["cost_usd"] += float(value)
            continue

        bits = rest.split(":")
        if len(bits) < 3:
            continue
        kind, safe_model = bits[0], bits[1]
        if kind not in {"chat", "embed"}:
            continue
        model = _display_model(safe_model)
        mk = f"{kind}:{model}"
        entry = by_model.setdefault(mk, _empty_model_entry(kind, model))
        if bits[2] == "day" and len(bits) >= 5:
            if bits[3] != day:
                continue
            field = bits[4]
            if field == "count":
                entry["today_requests"] += int(value)
            elif field == "lat_sum":
                entry["today_latency_sum_ms"] += float(value)
            elif field == "errors":
                entry["today_errors"] += int(value)
            elif field == "blocked":
                entry["today_blocked"] += int(value)
            elif field == "tok_in":
                entry["today_prompt_tokens"] += int(value)
            elif field == "tok_out":
                entry["today_completion_tokens"] += int(value)
            elif field == "tok_total":
                entry["today_total_tokens"] += int(value)
            elif field == "cost_sum":
                entry["today_cost_usd"] += float(value)
        else:
            field = bits[2]
            if field == "count":
                entry["requests"] += int(value)
            elif field == "lat_sum":
                entry["latency_sum_ms"] += float(value)
            elif field == "errors":
                entry["errors"] += int(value)
            elif field == "blocked":
                entry["blocked"] += int(value)
            elif field == "tok_in":
                entry["prompt_tokens"] += int(value)
            elif field == "tok_out":
                entry["completion_tokens"] += int(value)
            elif field == "tok_total":
                entry["total_tokens"] += int(value)
            elif field == "cost_sum":
                entry["cost_usd"] += float(value)

    models = []
    chat_req = chat_lat = embed_req = embed_lat = 0.0
    today_chat = today_embed = 0
    today_chat_lat = today_embed_lat = 0.0
    tok_total = tok_today = 0
    cost_total = cost_today = 0.0

    for entry in by_model.values():
        req = entry["requests"]
        avg = (entry["latency_sum_ms"] / req) if req else None
        today_req = entry["today_requests"]
        today_avg = (entry["today_latency_sum_ms"] / today_req) if today_req else None
        row = {
            "kind": entry["kind"],
            "model": entry["model"],
            "requests": req,
            "errors": entry["errors"],
            "blocked": entry["blocked"],
            "avg_latency_ms": round(avg, 1) if avg is not None else None,
            "today_requests": today_req,
            "today_avg_latency_ms": round(today_avg, 1) if today_avg is not None else None,
            "today_blocked": entry["today_blocked"],
            "prompt_tokens": entry["prompt_tokens"],
            "completion_tokens": entry["completion_tokens"],
            "total_tokens": entry["total_tokens"],
            "cost_usd": round(entry["cost_usd"], 6),
            "today_prompt_tokens": entry["today_prompt_tokens"],
            "today_completion_tokens": entry["today_completion_tokens"],
            "today_total_tokens": entry["today_total_tokens"],
            "today_cost_usd": round(entry["today_cost_usd"], 6),
        }
        models.append(row)
        tok_total += entry["total_tokens"]
        tok_today += entry["today_total_tokens"]
        cost_total += entry["cost_usd"]
        cost_today += entry["today_cost_usd"]
        if entry["kind"] == "chat":
            chat_req += req
            chat_lat += entry["latency_sum_ms"]
            today_chat += today_req
            today_chat_lat += entry["today_latency_sum_ms"]
        else:
            embed_req += req
            embed_lat += entry["latency_sum_ms"]
            today_embed += today_req
            today_embed_lat += entry["today_latency_sum_ms"]

    models.sort(key=lambda m: (-m["today_requests"], -m["requests"], m["model"]))
    providers = sorted(
        [
            {
                "provider": e["provider"],
                "requests": e["requests"],
                "total_tokens": e["total_tokens"],
                "cost_usd": round(e["cost_usd"], 6),
                "today_requests": e["today_requests"],
                "today_total_tokens": e["today_total_tokens"],
                "today_cost_usd": round(e["today_cost_usd"], 6),
            }
            for e in by_provider.values()
        ],
        key=lambda p: (-p["today_cost_usd"], -p["today_requests"], p["provider"]),
    )
    applications = _serialize_named(by_application)
    domains = _serialize_named(by_domain)

    return {
        "started_at": _started_at,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "backend": "redis" if _client() is not None else "memory",
        "totals": {
            "chat_requests": int(chat_req),
            "embed_requests": int(embed_req),
            "avg_chat_latency_ms": round(chat_lat / chat_req, 1) if chat_req else None,
            "avg_embed_latency_ms": round(embed_lat / embed_req, 1) if embed_req else None,
            "guardrails_blocked": int(blocked_total),
            "total_tokens": int(tok_total),
            "cost_usd": round(cost_total, 6),
        },
        "today": {
            "date": day,
            "chat_requests": int(today_chat),
            "embed_requests": int(today_embed),
            "avg_chat_latency_ms": round(today_chat_lat / today_chat, 1) if today_chat else None,
            "avg_embed_latency_ms": round(today_embed_lat / today_embed, 1) if today_embed else None,
            "guardrails_blocked": int(blocked_today),
            "total_tokens": int(tok_today),
            "cost_usd": round(cost_today, 6),
        },
        "by_model": models,
        "by_provider": providers,
        "by_application": applications,
        "by_domain": domains,
    }


class Timer:
    def __init__(self) -> None:
        self._t0 = time.perf_counter()

    def ms(self) -> float:
        return (time.perf_counter() - self._t0) * 1000.0
