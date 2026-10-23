"""Keep secrets out of Postgres/Redis/API responses; niyan.yaml is authoritative.

Secret fields: admin_auth.password, admin_auth.jwt_secret, proxy.api_keys,
providers.*.api_key, observability.secret_key.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from app.schemas.models import NiyanConfig
from app.secrets_policy import MASK, is_insecure

PROVIDERS = ("openai", "gemini", "anthropic", "vllm")


def strip_secrets(config: NiyanConfig) -> Dict[str, Any]:
    """JSON payload safe for Postgres / Redis (no secret values)."""
    data = config.model_dump(mode="json")
    data.setdefault("admin_auth", {})
    data["admin_auth"]["password"] = ""
    data["admin_auth"]["jwt_secret"] = ""
    data.setdefault("proxy", {})["api_keys"] = []
    for name in PROVIDERS:
        prov = (data.get("providers") or {}).get(name)
        if isinstance(prov, dict):
            prov["api_key"] = ""
    if isinstance(data.get("observability"), dict):
        data["observability"]["secret_key"] = ""
    return data


def has_secrets(payload: Dict[str, Any]) -> bool:
    """True if a stored payload still carries any secret value (legacy rows)."""
    if not isinstance(payload, dict):
        return False
    auth = payload.get("admin_auth") or {}
    if auth.get("password") or auth.get("jwt_secret"):
        return True
    if (payload.get("proxy") or {}).get("api_keys"):
        return True
    for name in PROVIDERS:
        if ((payload.get("providers") or {}).get(name) or {}).get("api_key"):
            return True
    return bool((payload.get("observability") or {}).get("secret_key"))


def overlay_secrets(config: NiyanConfig, source: NiyanConfig) -> NiyanConfig:
    """Copy secret fields from ``source`` (niyan.yaml) onto ``config``."""
    cfg = config.model_copy(deep=True)
    cfg.admin_auth.password = source.admin_auth.password
    cfg.admin_auth.jwt_secret = source.admin_auth.jwt_secret
    cfg.proxy.api_keys = list(source.proxy.api_keys)
    for name in PROVIDERS:
        getattr(cfg.providers, name).api_key = getattr(source.providers, name).api_key
    cfg.observability.secret_key = source.observability.secret_key
    return cfg


def merge_incoming(new: NiyanConfig, current: Optional[NiyanConfig]) -> NiyanConfig:
    """Never let a write (admin UI, API) replace real secrets with masked/default values."""
    cfg = new.model_copy(deep=True)
    if current is None:
        current = NiyanConfig()
    if is_insecure(cfg.admin_auth.password):
        cfg.admin_auth.password = current.admin_auth.password
    if is_insecure(cfg.admin_auth.jwt_secret):
        cfg.admin_auth.jwt_secret = current.admin_auth.jwt_secret
    keys = [k for k in cfg.proxy.api_keys if not is_insecure(k)]
    cfg.proxy.api_keys = keys or list(current.proxy.api_keys)
    for name in PROVIDERS:
        p_new, p_cur = getattr(cfg.providers, name), getattr(current.providers, name)
        if p_new.api_key == MASK:
            p_new.api_key = p_cur.api_key
    if cfg.observability.secret_key == MASK:
        cfg.observability.secret_key = current.observability.secret_key
    return cfg


def mask_secrets(config: NiyanConfig) -> NiyanConfig:
    """Copy for API responses: secret values replaced by a mask."""
    cfg = config.model_copy(deep=True)
    cfg.admin_auth.password = MASK if cfg.admin_auth.password else ""
    cfg.admin_auth.jwt_secret = MASK if cfg.admin_auth.jwt_secret else ""
    cfg.proxy.api_keys = [MASK for _ in cfg.proxy.api_keys]
    for name in PROVIDERS:
        p = getattr(cfg.providers, name)
        p.api_key = MASK if p.api_key else ""
    cfg.observability.secret_key = MASK if cfg.observability.secret_key else ""
    return cfg


def write_private(path: Path, text: str) -> None:
    """Write a file created 0600 (no world-readable window)."""
    path = Path(path)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
