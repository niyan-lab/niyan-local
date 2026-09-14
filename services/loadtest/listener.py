"""Write live.json progress snapshots during a Locust run."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict

from locust import events
from locust.runners import WorkerRunner

_last_write = 0.0
_WRITE_INTERVAL = 2.0
_total_tokens = 0
_run_started_at = 0.0


def _out_dir() -> Path:
    return Path(os.environ.get("LOADTEST_OUT_DIR", "/data/loadtests/current"))


def _write_live(environment: Any) -> None:
    global _last_write
    now = time.time()
    if now - _last_write < _WRITE_INTERVAL:
        return
    _last_write = now

    stats = environment.stats
    total = stats.total
    started = _run_started_at or getattr(environment.runner, "start_time", None) or now
    # Locust may store start_time as seconds; guard against weird units.
    if started > 1e12:  # ms
        started = started / 1000.0
    elapsed = max(0.01, now - float(started))

    fail_pct = 0.0
    if total.num_requests:
        fail_pct = round(100.0 * total.num_failures / total.num_requests, 2)

    payload: Dict[str, Any] = {
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_sec": round(elapsed, 1),
        "users": getattr(environment.runner, "user_count", 0) if environment.runner else 0,
        "requests": total.num_requests,
        "failures": total.num_failures,
        "fail_percent": fail_pct,
        "rps": round(total.current_rps, 2)
        if hasattr(total, "current_rps")
        else round(total.num_requests / elapsed, 2),
        "latency_ms": {
            "avg": round(total.avg_response_time or 0, 1),
            "p50": round(total.get_response_time_percentile(0.5) or 0, 1),
            "p95": round(total.get_response_time_percentile(0.95) or 0, 1),
            "p99": round(total.get_response_time_percentile(0.99) or 0, 1),
            "max": round(total.max_response_time or 0, 1),
        },
        "total_tokens": _total_tokens,
    }
    out = _out_dir() / "live.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))


def add_tokens(n: int) -> None:
    global _total_tokens
    if n and n > 0:
        _total_tokens += int(n)


@events.init.add_listener
def on_init(environment, **_kwargs):  # type: ignore[no-untyped-def]
    global _run_started_at
    _run_started_at = time.time()
    if isinstance(environment.runner, WorkerRunner):
        return

    @events.request.add_listener
    def _on_request(**_kw):  # type: ignore[no-untyped-def]
        _write_live(environment)

    @events.spawning_complete.add_listener
    def _on_spawn(**_kw):  # type: ignore[no-untyped-def]
        _write_live(environment)

    @events.quit.add_listener
    def _on_quit(**_kw):  # type: ignore[no-untyped-def]
        _write_live(environment)
