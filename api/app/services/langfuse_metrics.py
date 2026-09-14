"""Pull historical usage/cost from Langfuse Daily Metrics API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx

from app.schemas.models import ModelProvider, NiyanConfig
from app.settings import settings


PROPRIETARY = {
    ModelProvider.openai.value,
    ModelProvider.gemini.value,
    ModelProvider.anthropic.value,
}


def resolve_range(
    range_key: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Tuple[datetime, datetime, str]:
    """Return (from_ts, to_ts, label) in UTC."""
    now = datetime.now(timezone.utc)
    to_ts = now

    if from_date or to_date:
        try:
            from_ts = (
                datetime.fromisoformat(from_date.replace("Z", "+00:00"))
                if from_date
                else now - timedelta(days=7)
            )
            if from_ts.tzinfo is None:
                from_ts = from_ts.replace(tzinfo=timezone.utc)
            if to_date:
                to_ts = datetime.fromisoformat(to_date.replace("Z", "+00:00"))
                if to_ts.tzinfo is None:
                    to_ts = to_ts.replace(tzinfo=timezone.utc)
            label = "custom"
            return from_ts, to_ts, label
        except Exception:
            pass

    key = (range_key or "7d").strip().lower()
    mapping = {
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
        "90d": timedelta(days=90),
    }
    delta = mapping.get(key, timedelta(days=7))
    label = key if key in mapping else "7d"
    return now - delta, to_ts, label


def _model_provider_map(cfg: NiyanConfig) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for m in cfg.models:
        prov = m.provider.value if hasattr(m.provider, "value") else str(m.provider)
        out[m.id] = prov
        # Langfuse sometimes stores bare names
        if ":" in m.id:
            out[m.id.split(":")[0]] = prov
    return out


def classify_provider(model: str, mapping: Dict[str, str]) -> str:
    if model in mapping:
        return mapping[model]
    mid = (model or "").lower()
    if mid.startswith("gpt-") or mid.startswith("o1") or mid.startswith("o3"):
        return "openai"
    if mid.startswith("gemini"):
        return "gemini"
    if mid.startswith("claude") or "anthropic" in mid:
        return "anthropic"
    if mid.startswith("nomic") or "embed" in mid:
        return "ollama"
    return mapping.get(mid, "ollama")


async def fetch_daily_metrics(
    *,
    public_key: str,
    secret_key: str,
    from_ts: datetime,
    to_ts: datetime,
    base_url: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Paginate GET /api/public/metrics/daily."""
    if not (public_key and secret_key):
        return []

    host = (base_url or settings.langfuse_url).rstrip("/")
    from_iso = from_ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    to_iso = to_ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    rows: List[Dict[str, Any]] = []
    page = 1
    async with httpx.AsyncClient(timeout=20.0) as client:
        while page <= 50:
            url = (
                f"{host}/api/public/metrics/daily"
                f"?fromTimestamp={quote(from_iso)}"
                f"&toTimestamp={quote(to_iso)}"
                f"&page={page}&limit={limit}"
            )
            r = await client.get(url, auth=(public_key, secret_key))
            if r.status_code >= 400:
                raise RuntimeError(f"Langfuse metrics/daily HTTP {r.status_code}: {r.text[:300]}")
            payload = r.json()
            chunk = payload.get("data") or []
            if not isinstance(chunk, list):
                break
            rows.extend(chunk)
            meta = payload.get("meta") or {}
            total_pages = int(meta.get("totalPages") or 1)
            if page >= total_pages or not chunk:
                break
            page += 1
    return rows


def aggregate_daily(
    days: List[Dict[str, Any]],
    cfg: NiyanConfig,
) -> Dict[str, Any]:
    """Normalize Langfuse daily rows into dashboard traffic shape."""
    mapping = _model_provider_map(cfg)
    by_model: Dict[str, Dict[str, Any]] = {}
    by_provider: Dict[str, Dict[str, Any]] = {}
    timeseries: List[Dict[str, Any]] = []

    total_cost = 0.0
    total_tokens = 0
    total_traces = 0
    proprietary_cost = 0.0
    proprietary_tokens = 0
    proprietary_req = 0
    local_tokens = 0
    local_req = 0

    for day in days:
        date = day.get("date") or ""
        day_cost = float(day.get("totalCost") or 0)
        day_traces = int(day.get("countTraces") or 0)
        day_tokens = 0
        day_prop_cost = 0.0

        usage_list = day.get("usage") or []
        for u in usage_list:
            model = str(u.get("model") or "unknown")
            tokens = int(u.get("totalUsage") or 0)
            if not tokens:
                tokens = int(u.get("inputUsage") or 0) + int(u.get("outputUsage") or 0)
            cost = float(u.get("totalCost") or 0)
            req = int(u.get("countTraces") or u.get("countObservations") or 0)
            day_tokens += tokens

            entry = by_model.setdefault(
                model,
                {
                    "model": model,
                    "kind": "chat",
                    "requests": 0,
                    "total_tokens": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cost_usd": 0.0,
                    "provider": classify_provider(model, mapping),
                },
            )
            entry["requests"] += req
            entry["total_tokens"] += tokens
            entry["prompt_tokens"] += int(u.get("inputUsage") or 0)
            entry["completion_tokens"] += int(u.get("outputUsage") or 0)
            entry["cost_usd"] += cost

            prov = entry["provider"]
            pentry = by_provider.setdefault(
                prov,
                {
                    "provider": prov,
                    "requests": 0,
                    "total_tokens": 0,
                    "cost_usd": 0.0,
                },
            )
            pentry["requests"] += req
            pentry["total_tokens"] += tokens
            # Local/OSS cost deferred — only trust Langfuse cost for proprietary
            if prov in PROPRIETARY:
                pentry["cost_usd"] += cost
                proprietary_cost += cost
                proprietary_tokens += tokens
                proprietary_req += req
                day_prop_cost += cost
            else:
                local_tokens += tokens
                local_req += req

        total_cost += day_cost
        # Prefer summing proprietary from usage; keep Langfuse day total as fallback display
        total_tokens += day_tokens
        total_traces += day_traces
        timeseries.append(
            {
                "date": date,
                "total_tokens": day_tokens,
                "cost_usd": round(day_prop_cost, 6),
                "traces": day_traces,
            }
        )

    timeseries.sort(key=lambda x: x.get("date") or "")

    models = sorted(
        [
            {
                **m,
                "cost_usd": round(m["cost_usd"], 6)
                if m.get("provider") in PROPRIETARY
                else None,
            }
            for m in by_model.values()
        ],
        key=lambda m: (-(m.get("cost_usd") or 0), -m["total_tokens"], m["model"]),
    )
    providers = sorted(
        [
            {
                **p,
                "cost_usd": round(p["cost_usd"], 6) if p["provider"] in PROPRIETARY else None,
            }
            for p in by_provider.values()
        ],
        key=lambda p: (-(p.get("cost_usd") or 0), -p["requests"], p["provider"]),
    )

    return {
        "source": "langfuse",
        "period": {
            "chat_requests": total_traces,
            "total_tokens": total_tokens,
            "cost_usd": round(proprietary_cost, 6),
            "langfuse_total_cost_usd": round(total_cost, 6),
        },
        "timeseries": timeseries,
        "by_model": models,
        "by_provider": providers,
        "comparison": {
            "local": {
                "requests": local_req,
                "tokens": local_tokens,
                "cost_usd": None,
                "api_cost_note": "Open-source cost TBD",
                "label": "Self-hosted (Ollama)",
            },
            "proprietary": {
                "requests": proprietary_req,
                "tokens": proprietary_tokens,
                "cost_usd": round(proprietary_cost, 6),
                "label": "Proprietary (OpenAI + Gemini + Anthropic)",
                "openai": _provider_bucket(providers, "openai"),
                "gemini": _provider_bucket(providers, "gemini"),
                "anthropic": _provider_bucket(providers, "anthropic"),
            },
            "note": (
                "Tokens and proprietary API cost come from Langfuse. "
                "Open-source model cost will be added later."
            ),
        },
    }


def _provider_bucket(providers: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
    for p in providers:
        if p.get("provider") == name:
            return {
                "requests": p.get("requests", 0),
                "tokens": p.get("total_tokens", 0),
                "cost_usd": p.get("cost_usd"),
            }
    return {"requests": 0, "tokens": 0, "cost_usd": None}


async def load_langfuse_traffic(
    cfg: NiyanConfig,
    *,
    range_key: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict[str, Any]:
    """High-level helper for the dashboard router."""
    from_ts, to_ts, label = resolve_range(range_key, from_date, to_date)
    keys_ok = bool(cfg.observability.public_key and cfg.observability.secret_key)
    if not (cfg.observability.enabled and keys_ok):
        return {
            "source": "unavailable",
            "range": label,
            "from": from_ts.isoformat(),
            "to": to_ts.isoformat(),
            "error": "Langfuse keys not configured",
            "period": {"chat_requests": 0, "total_tokens": 0, "cost_usd": None},
            "timeseries": [],
            "by_model": [],
            "by_provider": [],
            "comparison": None,
        }

    try:
        days = await fetch_daily_metrics(
            public_key=cfg.observability.public_key,
            secret_key=cfg.observability.secret_key,
            from_ts=from_ts,
            to_ts=to_ts,
        )
        agg = aggregate_daily(days, cfg)
        agg["range"] = label
        agg["from"] = from_ts.isoformat()
        agg["to"] = to_ts.isoformat()
        agg["available"] = True
        return agg
    except Exception as exc:
        return {
            "source": "unavailable",
            "available": False,
            "range": label,
            "from": from_ts.isoformat(),
            "to": to_ts.isoformat(),
            "error": str(exc),
            "period": {"chat_requests": 0, "total_tokens": 0, "cost_usd": None},
            "timeseries": [],
            "by_model": [],
            "by_provider": [],
            "comparison": None,
        }
