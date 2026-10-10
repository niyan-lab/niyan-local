"""SSRF checks, filesystem jobs, and Locust orchestration for load tests."""

from __future__ import annotations

import ipaddress
import json
import logging
import socket
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import HTTPException

from app.container import get_container
from app.schemas.loadtest import (
    LoadTestCreate,
    LoadTestProgress,
    LoadTestRun,
    LoadTestStatus,
    LoadTestSummary,
    LoadTestTarget,
)
from app.settings import settings

logger = logging.getLogger(__name__)

MAX_USERS = 50
MAX_DURATION_SEC = 600
MIN_DURATION_SEC = 5

_ACTIVE_LOCK = threading.Lock()
_WATCHERS: Dict[str, threading.Thread] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def loadtests_root() -> Path:
    root = settings.niyan_root / "data" / "loadtests"
    root.mkdir(parents=True, exist_ok=True)
    return root


def run_dir(run_id: str) -> Path:
    return loadtests_root() / run_id


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _is_private_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return bool(
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
    )


def validate_custom_url(url: str, *, allow_internal: bool = False) -> str:
    """Raise HTTPException if URL is unsafe for SSRF."""
    raw = (url or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="custom url is required")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="url must be http or https")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise HTTPException(status_code=400, detail="url host is required")
    if host in {"metadata.google.internal", "metadata", "localhost"} or host.endswith(
        ".localhost"
    ):
        raise HTTPException(status_code=400, detail="blocked host")
    if host.startswith("169.254.") or host == "metadata.google":
        raise HTTPException(status_code=400, detail="blocked metadata host")

    # Resolve DNS and check IPs
    try:
        infos = socket.getaddrinfo(host, parsed.port or 80, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise HTTPException(status_code=400, detail=f"cannot resolve host: {exc}") from exc

    if not allow_internal:
        for info in infos:
            ip = info[4][0]
            if _is_private_ip(ip):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"internal/private URL blocked ({ip}). "
                        "Enable 'Allow internal URLs' to test private endpoints."
                    ),
                )
    return raw


def presets() -> List[Dict[str, Any]]:
    return [
        {
            "id": "gateway_chat",
            "label": "Gateway chat completions",
            "path": "/v1/chat/completions",
            "fields": ["model", "messages", "auth_bearer", "users", "spawn_rate", "duration_sec"],
        },
        {
            "id": "gateway_embeddings",
            "label": "Gateway embeddings",
            "path": "/v1/embeddings",
            "fields": ["model", "input", "auth_bearer", "users", "spawn_rate", "duration_sec"],
        },
        {
            "id": "gateway_domain",
            "label": "Gateway domain (Enterprise AI Policy)",
            "path": "/v1/chat/completions",
            "fields": ["model", "messages", "auth_bearer", "users", "spawn_rate", "duration_sec"],
            "note": "Set model to a domain id (e.g. finance, summary).",
        },
        {
            "id": "custom",
            "label": "Custom HTTP endpoint",
            "fields": [
                "url",
                "method",
                "headers",
                "body",
                "auth_bearer",
                "allow_internal_urls",
                "users",
                "spawn_rate",
                "duration_sec",
            ],
        },
    ]


def _cost_warning(body: LoadTestCreate) -> Optional[str]:
    model = (body.model or "").lower()
    if body.target_type == LoadTestTarget.custom:
        return None
    if model.startswith("gpt-") or model.startswith("o1") or model.startswith("o3"):
        return "This run may call OpenAI and incur API cost. Keep users/duration low."
    if model.startswith("gemini"):
        return "This run may call Gemini and incur API cost. Keep users/duration low."
    if model.startswith("claude"):
        return "This run may call Anthropic and incur API cost. Keep users/duration low."
    if body.target_type == LoadTestTarget.gateway_domain:
        return (
            "Domain routing may hit a proprietary model if Enterprise AI Policy "
            "deployment is set to Proprietary."
        )
    return None


def _build_job(body: LoadTestCreate) -> Dict[str, Any]:
    users = min(max(body.users, 1), MAX_USERS)
    duration = min(max(body.duration_sec, MIN_DURATION_SEC), MAX_DURATION_SEC)
    spawn = min(max(float(body.spawn_rate), 0.1), float(MAX_USERS))

    job: Dict[str, Any] = {
        "target_type": body.target_type.value,
        "auth_bearer": (body.auth_bearer or "sk-niyan-local").strip(),
        "host": (body.host or settings.gateway_url).rstrip("/"),
        "users": users,
        "spawn_rate": spawn,
        "duration_sec": duration,
    }

    if body.target_type in {LoadTestTarget.gateway_chat, LoadTestTarget.gateway_domain}:
        job["model"] = (body.model or ("finance" if body.target_type == LoadTestTarget.gateway_domain else "llama3.2:3b")).strip()
        job["messages"] = body.messages or [
            {"role": "user", "content": "Say hi in five words."}
        ]
    elif body.target_type == LoadTestTarget.gateway_embeddings:
        job["model"] = (body.model or "nomic-embed-text").strip()
        job["input"] = body.input or "Niyan load test embedding input"
    elif body.target_type == LoadTestTarget.custom:
        url = validate_custom_url(body.url or "", allow_internal=body.allow_internal_urls)
        job["url"] = url
        job["method"] = (body.method or "POST").upper()
        job["headers"] = body.headers or {}
        job["body"] = body.body
        job["allow_internal_urls"] = body.allow_internal_urls
        # Locust host derived from URL inside locustfile
        parsed = urlparse(url)
        job["host"] = f"{parsed.scheme}://{parsed.netloc}"

    return job


def find_active_run_id() -> Optional[str]:
    for path in sorted(loadtests_root().glob("*/run.json"), reverse=True):
        data = _read_json(path)
        if data and data.get("status") == LoadTestStatus.running.value:
            return data.get("id")
    return None


def list_runs(limit: int = 50) -> List[LoadTestRun]:
    runs: List[LoadTestRun] = []
    dirs = sorted(
        [p for p in loadtests_root().iterdir() if p.is_dir() and (p / "run.json").exists()],
        key=lambda p: p.name,
        reverse=True,
    )
    for d in dirs[:limit]:
        _repair_false_failure(d.name)
        run = get_run(d.name)
        if run:
            runs.append(run)
    return runs


def _artifacts(d: Path) -> Dict[str, bool]:
    return {
        "summary_json": (d / "summary.json").exists(),
        "report_html": (d / "report.html").exists(),
        "stats_csv": (d / "run_stats.csv").exists() or (d / "stats_stats.csv").exists(),
        "live_json": (d / "live.json").exists(),
    }


def _parse_started_at(meta: Dict[str, Any]) -> Optional[float]:
    raw = meta.get("started_at") or meta.get("created_at")
    if not raw:
        return None
    try:
        # 2026-07-29T12:54:31Z
        dt = datetime.strptime(str(raw), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _repair_false_failure(run_id: str) -> None:
    """If a run was marked failed but Locust did produce metrics/report, mark finished."""
    d = run_dir(run_id)
    meta = _read_json(d / "run.json")
    if not meta or meta.get("status") != LoadTestStatus.failed.value:
        return
    live = _read_json(d / "live.json") or {}
    has_report = (d / "report.html").exists()
    requests = int(live.get("requests") or 0)
    if not has_report and requests <= 0:
        return
    meta["status"] = LoadTestStatus.finished.value
    meta["error"] = None
    if not meta.get("finished_at"):
        meta["finished_at"] = live.get("updated_at") or _now_iso()
    _write_json(d / "run.json", meta)
    _finalize_summary(run_id, status=LoadTestStatus.finished, force=True)


def get_run(run_id: str) -> Optional[LoadTestRun]:
    d = run_dir(run_id)
    meta = _read_json(d / "run.json")
    if not meta:
        return None
    _repair_false_failure(run_id)
    # Refresh status if Locust finished
    _maybe_finalize(run_id)
    meta = _read_json(d / "run.json") or meta

    progress_raw = _read_json(d / "live.json")
    summary_raw = _read_json(d / "summary.json")
    progress = LoadTestProgress(**progress_raw) if progress_raw else None
    summary = None
    if summary_raw and isinstance(summary_raw.get("metrics"), dict):
        summary = LoadTestSummary(**summary_raw["metrics"])
    elif summary_raw:
        try:
            summary = LoadTestSummary(
                **{k: summary_raw[k] for k in LoadTestSummary.model_fields if k in summary_raw}
            )
        except Exception:
            summary = None

    return LoadTestRun(
        id=meta["id"],
        name=meta.get("name"),
        status=LoadTestStatus(meta.get("status") or "queued"),
        target_type=LoadTestTarget(meta.get("target_type") or "gateway_chat"),
        created_at=meta.get("created_at") or "",
        started_at=meta.get("started_at"),
        finished_at=meta.get("finished_at"),
        error=meta.get("error"),
        job=meta.get("job") or {},
        progress=progress,
        summary=summary,
        cost_warning=meta.get("cost_warning"),
        artifacts=_artifacts(d),
    )


def create_and_start(body: LoadTestCreate) -> LoadTestRun:
    with _ACTIVE_LOCK:
        active = find_active_run_id()
        if active:
            raise HTTPException(
                status_code=409,
                detail=f"Another load test is already running ({active}). Stop it first.",
            )

        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
        d = run_dir(run_id)
        d.mkdir(parents=True, exist_ok=True)

        job = _build_job(body)
        warning = _cost_warning(body)
        _write_json(d / "job.json", job)

        meta = {
            "id": run_id,
            "name": body.name or f"{body.target_type.value}-{job.get('users')}u",
            "status": LoadTestStatus.queued.value,
            "target_type": body.target_type.value,
            "created_at": _now_iso(),
            "started_at": None,
            "finished_at": None,
            "error": None,
            "job": job,
            "cost_warning": warning,
        }
        _write_json(d / "run.json", meta)

        try:
            get_container().orchestrator.start_loadtest(
                run_id=run_id,
                job_path=f"/data/loadtests/{run_id}/job.json",
                out_dir=f"/data/loadtests/{run_id}",
                users=int(job["users"]),
                spawn_rate=float(job["spawn_rate"]),
                duration_sec=int(job["duration_sec"]),
                host=str(job.get("host") or settings.gateway_url),
                # Only consumed on Kubernetes, where there is no filesystem shared
                # between niyan-api and the ephemeral loadtest Job pod: the job
                # config is delivered via env var instead. Ignored on VM/docker,
                # which already shares a bind-mounted job.json path.
                job_body=job,
            )
        except Exception as exc:
            meta["status"] = LoadTestStatus.failed.value
            meta["error"] = str(exc)
            meta["finished_at"] = _now_iso()
            _write_json(d / "run.json", meta)
            raise HTTPException(status_code=503, detail=f"failed to start loadtest: {exc}") from exc

        meta["status"] = LoadTestStatus.running.value
        meta["started_at"] = _now_iso()
        _write_json(d / "run.json", meta)

        t = threading.Thread(target=_watch_run, args=(run_id,), daemon=True)
        _WATCHERS[run_id] = t
        t.start()

    # Do not call get_run() here — it would race Locust startup and false-fail.
    return LoadTestRun(
        id=run_id,
        name=meta.get("name"),
        status=LoadTestStatus.running,
        target_type=LoadTestTarget(meta["target_type"]),
        created_at=meta["created_at"],
        started_at=meta.get("started_at"),
        job=job,
        cost_warning=warning,
        artifacts=_artifacts(d),
    )


def stop_run(run_id: str) -> LoadTestRun:
    d = run_dir(run_id)
    meta = _read_json(d / "run.json")
    if not meta:
        raise HTTPException(status_code=404, detail="run not found")
    if meta.get("status") != LoadTestStatus.running.value:
        raise HTTPException(status_code=400, detail=f"run is not running ({meta.get('status')})")
    try:
        get_container().orchestrator.stop_loadtest(run_id=run_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"failed to stop: {exc}") from exc
    meta["status"] = LoadTestStatus.stopped.value
    meta["finished_at"] = _now_iso()
    _write_json(d / "run.json", meta)
    _finalize_summary(run_id, status=LoadTestStatus.stopped)
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return run


def _watch_run(run_id: str) -> None:
    """Poll until Locust exits, then write summary."""
    d = run_dir(run_id)
    # Wait for Locust process (or first live.json) so we don't false-fail on startup race.
    saw_running = False
    for _ in range(40):  # up to ~20s
        if get_container().orchestrator.loadtest_is_running(run_id=run_id):
            saw_running = True
            break
        if (d / "live.json").exists() or (d / "report.html").exists():
            saw_running = True
            break
        time.sleep(0.5)

    meta = _read_json(d / "run.json") or {}
    duration = int((meta.get("job") or {}).get("duration_sec") or 60)
    deadline = time.time() + duration + 120

    if saw_running:
        while time.time() < deadline:
            running = get_container().orchestrator.loadtest_is_running(run_id=run_id)
            if not running:
                # Brief grace — Locust may flap during shutdown; confirm still gone.
                time.sleep(2)
                if not get_container().orchestrator.loadtest_is_running(run_id=run_id):
                    # Prefer waiting for report.html when duration nearly complete
                    if (d / "report.html").exists() or (d / "live.json").exists():
                        break
                    # If still within scheduled duration, keep waiting a bit
                    started = _parse_started_at(meta)
                    if started and (time.time() - started) < duration:
                        time.sleep(2)
                        continue
                    break
            time.sleep(2)
    _maybe_finalize(run_id)


def _sync_k8s_summary(run_id: str) -> None:
    """On Kubernetes, recover the run's metrics via the K8s API (Job/pod status +
    pod log) and stage them at the same local live.json path the rest of this
    module already reads — since there is no filesystem shared between niyan-api
    and the ephemeral loadtest Job pod (see D6). No-op on the VM/docker path,
    where DockerOrchestrator exposes no get_loadtest_summary and live.json is
    already written locally by the bind-mounted loadtest container.
    """
    orchestrator = get_container().orchestrator
    fetch = getattr(orchestrator, "get_loadtest_summary", None)
    if not callable(fetch):
        return
    d = run_dir(run_id)
    if (d / "live.json").exists():
        return  # already synced
    try:
        remote = fetch(run_id)
    except Exception:
        logger.warning("_sync_k8s_summary(%s): get_loadtest_summary raised", run_id, exc_info=True)
        remote = None
    if remote:
        _write_json(d / "live.json", remote)
    else:
        # Not necessarily an error (the pod log may just not have the marker
        # yet), but log it: a persistently missing/unparseable summary is what
        # silently degrades a completed K8s run to "failed" downstream.
        logger.debug(
            "_sync_k8s_summary(%s): no summary recovered from K8s API yet", run_id
        )


def _maybe_finalize(run_id: str) -> None:
    d = run_dir(run_id)
    meta = _read_json(d / "run.json")
    if not meta or meta.get("status") != LoadTestStatus.running.value:
        return
    if get_container().orchestrator.loadtest_is_running(run_id=run_id):
        return

    _sync_k8s_summary(run_id)

    live = _read_json(d / "live.json") or {}
    has_report = (d / "report.html").exists()
    requests = int(live.get("requests") or 0)
    started = _parse_started_at(meta)
    duration = int((meta.get("job") or {}).get("duration_sec") or 60)
    elapsed = (time.time() - started) if started else 9999

    # Startup race: Locust not visible yet and no artifacts — keep running.
    if not live and not has_report and elapsed < 15:
        return

    # Still within scheduled window with no proof Locust ever started — wait.
    if not live and not has_report and elapsed < duration + 5:
        return

    if live or has_report or requests > 0:
        status = LoadTestStatus.finished
        meta["error"] = None
    else:
        status = LoadTestStatus.failed
        meta["error"] = meta.get("error") or "Locust exited without live metrics"

    meta["status"] = status.value
    meta["finished_at"] = _now_iso()
    _write_json(d / "run.json", meta)
    _finalize_summary(run_id, status=status, force=True)


def _finalize_summary(run_id: str, *, status: LoadTestStatus, force: bool = False) -> None:
    d = run_dir(run_id)
    summary_path = d / "summary.json"
    if summary_path.exists() and status == LoadTestStatus.finished and not force:
        existing = _read_json(summary_path) or {}
        metrics = existing.get("metrics") or {}
        if int(metrics.get("requests") or 0) > 0:
            return
    live = _read_json(d / "live.json") or {}
    meta = _read_json(d / "run.json") or {}
    metrics = {
        "requests": live.get("requests", 0),
        "failures": live.get("failures", 0),
        "fail_percent": live.get("fail_percent", 0),
        "rps": live.get("rps", 0),
        "latency_ms": live.get("latency_ms") or {},
        "total_tokens": live.get("total_tokens", 0),
        "duration_sec": live.get("elapsed_sec")
        or (meta.get("job") or {}).get("duration_sec")
        or 0,
    }
    summary = {
        "id": run_id,
        "status": status.value,
        "finished_at": meta.get("finished_at") or _now_iso(),
        "job": meta.get("job") or {},
        "metrics": metrics,
    }
    _write_json(summary_path, summary)


def download_path(run_id: str, fmt: str) -> Path:
    d = run_dir(run_id)
    if not (d / "run.json").exists():
        raise HTTPException(status_code=404, detail="run not found")
    fmt = (fmt or "json").lower()
    if fmt == "json":
        path = d / "summary.json"
        if not path.exists():
            # fallback to live
            path = d / "live.json"
    elif fmt == "html":
        path = d / "report.html"
    elif fmt == "csv":
        path = d / "run_stats.csv"
        if not path.exists():
            path = d / "stats_stats.csv"
    else:
        raise HTTPException(status_code=400, detail="format must be json|html|csv")
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{fmt} report not ready yet")
    return path
