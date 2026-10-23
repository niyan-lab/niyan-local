"""Niyan OpenAI-compatible gateway: guardrails → LiteLLM → optional Langfuse."""

from __future__ import annotations

import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.openapi.utils import get_openapi
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

import metrics as gw_metrics
import pricing as gw_pricing
import policy as gw_policy
import runtime_config

LITELLM_URL = os.getenv("LITELLM_URL", "http://litellm:4001").rstrip("/")
LITELLM_KEY = os.getenv("LITELLM_MASTER_KEY", "")
MASTER_KEYS = {
    k.strip()
    for k in os.getenv("NIYAN_API_KEYS", LITELLM_KEY).split(",")
    if k.strip()
}
_INSECURE_KEYS = {"", "sk-niyan-local", "niyan"}
if os.getenv("NIYAN_ALLOW_INSECURE_DEFAULTS", "").lower() not in {"1", "true", "yes"}:
    if (
        LITELLM_KEY.strip() in _INSECURE_KEYS
        or "change-me" in LITELLM_KEY.lower()
        or not MASTER_KEYS
        or MASTER_KEYS & _INSECURE_KEYS
    ):
        raise SystemExit(
            "Refusing to start: LITELLM_MASTER_KEY / NIYAN_API_KEYS empty or default. "
            "Run ./install.sh (niyan secrets init) or set NIYAN_ALLOW_INSECURE_DEFAULTS=1 for dev only."
        )
GUARDRAILS_URL = os.getenv("GUARDRAILS_URL", "").rstrip("/")
GUARDRAILS_ENABLED = os.getenv("GUARDRAILS_ENABLED", "true").lower() == "true"
ON_FAILURE = os.getenv("GUARDRAILS_ON_FAILURE", "allow")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "").rstrip("/")
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")


def _read_yaml_observability() -> Optional[Dict[str, str]]:
    data = runtime_config.load()
    if data is None:
        return None
    obs = data.get("observability") or {}
    return {
        "public": str(obs.get("public_key") or ""),
        "secret": str(obs.get("secret_key") or ""),
        "host": str(obs.get("host") or ""),
    }


def _read_yaml_enterprise_policy() -> Optional[Dict[str, Any]]:
    data = runtime_config.load()
    if data is None:
        return None
    return data.get("enterprise_policy") or {}


def _langfuse_creds() -> tuple[str, str, str]:
    """Resolve (host, public_key, secret_key): niyan.yaml keys first, else env."""
    y = _read_yaml_observability()
    public = (y["public"] if y and y["public"] else LANGFUSE_PUBLIC_KEY) or ""
    secret = (y["secret"] if y and y["secret"] else LANGFUSE_SECRET_KEY) or ""
    host = LANGFUSE_HOST or (y["host"] if y and y["host"] else "")
    host = (host or "http://langfuse-web:3000").rstrip("/")
    if host in ("http://langfuse:3000", "http://langfuse"):
        host = "http://langfuse-web:3000"
    return host, public, secret

bearer_scheme = HTTPBearer(
    auto_error=True,
    description="Use your Niyan API key (`niyan gateway keys`) (Authorize with value only; Swagger adds Bearer).",
)

app = FastAPI(
    title="Niyan Gateway",
    version="0.1.0",
    description=(
        "OpenAI-compatible proxy for Niyan.\n\n"
        "**Try it here:** use **Authorize** with your API key (`niyan gateway keys`), then "
        "`POST /v1/chat/completions`.\n\n"
        "Note: the base path `/v1` alone is not a chat endpoint — use `/v1/chat/completions`."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


class ChatMessage(BaseModel):
    role: str = Field(..., examples=["user"])
    content: str = Field(..., examples=["Hello from Niyan"])


class ChatCompletionRequest(BaseModel):
    model: str = Field(
        ...,
        examples=["finance", "llama3.2:3b"],
        description=(
            "Model id or Enterprise AI Policy domain id "
            "(e.g. finance → remapped to local or proprietary model)"
        ),
    )
    messages: List[ChatMessage]
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    stream: bool = Field(default=False, description="Streaming not enabled in prototype")
    user: Optional[str] = Field(
        default=None,
        description="Optional OpenAI user id. Prefer X-Niyan-Application for project attribution.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "model": "llama3.2:3b",
                    "messages": [{"role": "user", "content": "Say hello in one short sentence."}],
                },
                {
                    "model": "llama3.2:3b",
                    "messages": [
                        {
                            "role": "user",
                            "content": "My SSN is 123-45-6789 — please help.",
                        }
                    ],
                },
            ]
        }
    }


class EmbeddingRequest(BaseModel):
    model: str = Field(
        default="nomic-embed-text",
        examples=["nomic-embed-text"],
        description="Embedding model id routed via LiteLLM → Ollama",
    )
    input: Any = Field(
        ...,
        description="String or list of strings to embed",
        examples=["Niyan local RAG stack"],
    )
    encoding_format: Optional[str] = Field(default=None, examples=["float"])
    dimensions: Optional[int] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "model": "nomic-embed-text",
                    "input": "What is Niyan?",
                }
            ]
        }
    }


def _check_key(credentials: HTTPAuthorizationCredentials = Security(bearer_scheme)) -> str:
    token = credentials.credentials.strip()
    if token not in MASTER_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return token


def _user_text(messages: List[ChatMessage]) -> str:
    parts = [m.content for m in messages if m.role == "user"]
    return "\n".join(parts) if parts else (messages[-1].content if messages else "")


_APP_CLEAN = re.compile(r"[^a-zA-Z0-9._:-]+")


def _application_id(request: Request, body_user: Optional[str] = None) -> str:
    """Resolve calling application/project for usage attribution.

    Clients should send `X-Niyan-Application` (aliases: X-Niyan-Project, X-Application-Id).
    Falls back to OpenAI `user` then `unattributed`.
    """
    headers = request.headers
    raw = (
        headers.get("x-niyan-application")
        or headers.get("x-niyan-project")
        or headers.get("x-application-id")
        or (body_user or "")
    )
    cleaned = _APP_CLEAN.sub("-", str(raw).strip()).strip("-._")[:64]
    return gw_metrics.canonicalize_application(cleaned)


async def _guard(stage: str, text: str) -> Dict[str, Any]:
    if not GUARDRAILS_ENABLED or not GUARDRAILS_URL:
        return {"allowed": True, "stage": stage, "skipped": True}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{GUARDRAILS_URL}/check",
                json={"stage": stage, "text": text},
            )
            if r.status_code >= 500 and ON_FAILURE == "allow":
                return {"allowed": True, "stage": stage, "error": r.text, "failed_open": True}
            r.raise_for_status()
            return r.json()
    except Exception as exc:
        if ON_FAILURE == "allow":
            return {"allowed": True, "stage": stage, "error": str(exc), "failed_open": True}
        raise HTTPException(status_code=503, detail=f"guardrails unavailable: {exc}") from exc


async def _langfuse_trace(
    *,
    trace_id: str,
    model: str,
    messages: List[ChatMessage],
    output_text: str,
    usage: Optional[Dict[str, Any]],
    guardrails_input: Dict[str, Any],
    guardrails_output: Dict[str, Any],
    provider: str = "ollama",
    domain: Optional[str] = None,
    policy_deployment: Optional[str] = None,
    requested_model: Optional[str] = None,
    application: str = "unattributed",
) -> Dict[str, Any]:
    """Send a Langfuse trace + generation (model + usage). Langfuse prices proprietary models."""
    host, public_key, secret_key = _langfuse_creds()
    if not (host and public_key and secret_key):
        return {
            "ok": False,
            "skipped": True,
            "reason": "Langfuse keys not set — add them under Admin → Observability",
        }

    ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    gen_id = str(uuid.uuid4())
    input_payload = [{"role": m.role, "content": m.content} for m in messages]
    usage_body: Dict[str, Any] = {}
    if usage:
        usage_body = {
            "input": usage.get("prompt_tokens"),
            "output": usage.get("completion_tokens"),
            "total": usage.get("total_tokens"),
            "unit": "TOKENS",
        }

    meta: Dict[str, Any] = {
        "guardrails_input": guardrails_input,
        "guardrails_output": guardrails_output,
        "source": "niyan-gateway",
        "provider": provider or "ollama",
        "application": application or "unattributed",
    }
    if domain:
        meta["domain"] = domain
    if policy_deployment:
        meta["policy_deployment"] = policy_deployment
    if requested_model and requested_model != model:
        meta["requested_model"] = requested_model
        meta["resolved_model"] = model

    tags = ["niyan", provider or "ollama", f"app:{application or 'unattributed'}"]
    if domain:
        tags.append(f"domain:{domain}")
    if policy_deployment:
        tags.append(f"deployment:{policy_deployment}")

    batch = [
        {
            "id": str(uuid.uuid4()),
            "type": "trace-create",
            "timestamp": ts,
            "body": {
                "id": trace_id,
                "name": "niyan-chat",
                "input": input_payload,
                "output": output_text,
                "metadata": meta,
                "tags": tags,
            },
        },
        {
            "id": str(uuid.uuid4()),
            "type": "generation-create",
            "timestamp": ts,
            "body": {
                "id": gen_id,
                "traceId": trace_id,
                "name": "chat-completion",
                "model": model,
                "input": input_payload,
                "output": output_text,
                "usage": usage_body,
                "metadata": meta,
            },
        },
    ]

    url = f"{host}/api/public/ingestion"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                url,
                auth=(public_key, secret_key),
                json={"batch": batch},
            )
            if r.status_code >= 400:
                return {
                    "ok": False,
                    "status_code": r.status_code,
                    "body": r.text[:500],
                    "host": host,
                }
            return {"ok": True, "status_code": r.status_code, "host": host, "trace_id": trace_id}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "host": host}


def custom_openapi() -> Dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schema["components"] = schema.get("components", {})
    schema["components"]["securitySchemes"] = {
        "HTTPBearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "API Key",
            "description": "Enter a key from niyan.yaml (`niyan gateway keys`).",
        }
    }
    schema["security"] = [{"HTTPBearer": []}]
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi  # type: ignore[method-assign]


@app.get("/", include_in_schema=False)
async def root() -> Dict[str, Any]:
    return {
        "name": "Niyan Gateway",
        "message": "OpenAI-compatible API. Use Swagger to send test requests.",
        "docs": "http://127.0.0.1:4000/docs",
        "redoc": "http://127.0.0.1:4000/redoc",
        "chat_completions": "POST /v1/chat/completions",
        "embeddings": "POST /v1/embeddings",
        "models": "GET /v1/models",
        "health": "GET /health",
        "default_api_key": "<your-key: niyan gateway keys>",
        "example_curl": (
            "curl http://127.0.0.1:4000/v1/chat/completions "
            '-H "Authorization: Bearer $NIYAN_API_KEY" '
            '-H "Content-Type: application/json" '
            '-d \'{"model":"llama3.2:3b","messages":[{"role":"user","content":"Hello"}]}\''
        ),
    }


@app.get("/v1", include_in_schema=False)
async def v1_root() -> Dict[str, Any]:
    return {
        "error": "Not a chat endpoint",
        "hint": "POST to /v1/chat/completions (or open /docs to try it in the browser)",
        "docs": "/docs",
        "endpoints": {
            "POST /v1/chat/completions": "Chat (OpenAI shape)",
            "POST /v1/embeddings": "Embeddings (OpenAI shape)",
            "GET /v1/models": "List models",
        },
    }


@app.get("/v1/docs", include_in_schema=False)
async def v1_docs_redirect() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["ops"])
async def health() -> Dict[str, Any]:
    """Liveness probe — no auth required. Includes Langfuse wiring status."""
    host, public_key, secret_key = _langfuse_creds()
    return {
        "status": "ok",
        "langfuse": {
            "host": host or None,
            "public_key_set": bool(public_key),
            "secret_key_set": bool(secret_key),
            "enabled": bool(host and public_key and secret_key),
        },
    }


@app.get("/metrics", tags=["ops"])
async def gateway_metrics(_: str = Depends(_check_key)) -> Dict[str, Any]:
    """High-level request / latency counters for the admin dashboard."""
    return gw_metrics.snapshot()


@app.get("/v1/models", tags=["OpenAI"])
async def list_models(_: str = Depends(_check_key)) -> Any:
    """List models known to LiteLLM / Ollama."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(
            f"{LITELLM_URL}/v1/models",
            headers={"Authorization": f"Bearer {LITELLM_KEY}"},
        )
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()


@app.post("/v1/embeddings", tags=["OpenAI"])
async def embeddings(
    body: EmbeddingRequest,
    request: Request,
    _: str = Depends(_check_key),
) -> Any:
    """OpenAI Embeddings — LiteLLM → Ollama (e.g. nomic-embed-text)."""
    payload = body.model_dump(exclude_none=True)
    application = _application_id(request)
    timer = gw_metrics.Timer()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                f"{LITELLM_URL}/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {LITELLM_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if r.status_code >= 400:
                gw_metrics.record(
                    "embed",
                    body.model,
                    timer.ms(),
                    error=True,
                    provider=gw_pricing.resolve_provider(body.model),
                    application=application,
                )
                raise HTTPException(status_code=r.status_code, detail=r.text)
            data = r.json()
            usage = data.get("usage") if isinstance(data, dict) else None
            prompt, completion, total = gw_pricing.usage_tokens(usage)
            provider = gw_pricing.resolve_provider(body.model)
            cost = gw_pricing.estimate_cost_usd(body.model, prompt, completion, provider=provider)
            gw_metrics.record(
                "embed",
                body.model,
                timer.ms(),
                prompt_tokens=prompt,
                completion_tokens=completion,
                total_tokens=total,
                cost_usd=cost,
                provider=provider,
                application=application,
            )
            return data
    except HTTPException:
        raise
    except Exception:
        gw_metrics.record(
            "embed",
            body.model,
            timer.ms(),
            error=True,
            provider=gw_pricing.resolve_provider(body.model),
            application=application,
        )
        raise


@app.post("/v1/chat/completions", tags=["OpenAI"])
async def chat_completions(
    body: ChatCompletionRequest,
    request: Request,
    _: str = Depends(_check_key),
) -> Any:
    """
    OpenAI Chat Completions.

    Flow: enterprise policy (domain→model) → guardrails (input) → LiteLLM → guardrails (output).
    Clients may pass a domain id as `model` (e.g. finance); the gateway remaps via Enterprise AI Policy.
    Send `X-Niyan-Application` so Dashboard can attribute usage to a project.
    """
    if body.stream:
        raise HTTPException(status_code=400, detail="streaming not enabled in prototype gateway")

    route = gw_policy.resolve_model(body.model, _read_yaml_enterprise_policy())
    if not route.ok:
        raise HTTPException(
            status_code=400,
            detail={"error": "enterprise_policy", "reason": route.error},
        )
    resolved_model = route.resolved_model
    application = _application_id(request, body.user)

    timer = gw_metrics.Timer()
    trace_id = str(uuid.uuid4())
    user_text = _user_text(body.messages)
    inbound = await _guard("input", user_text)
    provider = gw_pricing.resolve_provider(resolved_model)
    if not inbound.get("allowed", True):
        gw_metrics.record(
            "chat",
            resolved_model,
            timer.ms(),
            error=True,
            blocked=True,
            provider=provider,
            application=application,
            domain=route.domain,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error": "guardrails_blocked",
                "stage": "input",
                "reason": inbound.get("reason", "blocked"),
                "trace_id": trace_id,
                "application": application,
            },
        )

    payload = body.model_dump(exclude_none=True)
    payload["model"] = resolved_model
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                f"{LITELLM_URL}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {LITELLM_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if r.status_code >= 400:
                gw_metrics.record(
                    "chat",
                    resolved_model,
                    timer.ms(),
                    error=True,
                    provider=provider,
                    application=application,
                    domain=route.domain,
                )
                raise HTTPException(status_code=r.status_code, detail=r.text)
            data = r.json()
    except HTTPException:
        raise
    except Exception:
        gw_metrics.record(
            "chat",
            resolved_model,
            timer.ms(),
            error=True,
            provider=provider,
            application=application,
            domain=route.domain,
        )
        raise

    try:
        out_text = data["choices"][0]["message"]["content"]
    except Exception:
        out_text = ""

    outbound = await _guard("output", out_text or "")
    if not outbound.get("allowed", True):
        gw_metrics.record(
            "chat",
            resolved_model,
            timer.ms(),
            error=True,
            blocked=True,
            provider=provider,
            application=application,
            domain=route.domain,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error": "guardrails_blocked",
                "stage": "output",
                "reason": outbound.get("reason", "blocked"),
                "trace_id": trace_id,
                "application": application,
            },
        )

    if outbound.get("text") and out_text:
        data["choices"][0]["message"]["content"] = outbound["text"]
        out_text = outbound["text"]

    langfuse_status = await _langfuse_trace(
        trace_id=trace_id,
        model=resolved_model,
        messages=body.messages,
        output_text=out_text or "",
        usage=data.get("usage"),
        guardrails_input=inbound,
        guardrails_output=outbound,
        provider=provider,
        domain=route.domain,
        policy_deployment=route.deployment,
        requested_model=route.requested,
        application=application,
    )

    usage = data.get("usage") if isinstance(data, dict) else None
    prompt, completion, total = gw_pricing.usage_tokens(usage)
    hidden = (data.get("_hidden_params") or {}) if isinstance(data, dict) else {}
    response_cost = hidden.get("response_cost")
    cost = gw_pricing.estimate_cost_usd(
        resolved_model,
        prompt,
        completion,
        provider=provider,
        response_cost=response_cost if response_cost is not None else None,
    )
    gw_metrics.record(
        "chat",
        resolved_model,
        timer.ms(),
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        cost_usd=cost,
        provider=provider,
        application=application,
        domain=route.domain,
    )
    data["niyan"] = {
        "trace_id": trace_id,
        "guardrails_input": inbound,
        "guardrails_output": outbound,
        "langfuse": langfuse_status,
        "latency_ms": round(timer.ms(), 1),
        "provider": provider,
        "application": application,
        "requested_model": route.requested,
        "resolved_model": resolved_model,
        "domain": route.domain,
        "policy_deployment": route.deployment,
        "via_policy": route.via_policy,
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
            "cost_usd": round(cost, 6),
        },
    }
    return data
