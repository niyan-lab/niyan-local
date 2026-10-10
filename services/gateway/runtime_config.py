"""Runtime Niyan config: Redis (published by niyan-api) first, niyan.yaml fallback.

Keep Redis key names in sync with api/app/services/config_store.py.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

NIYAN_CONFIG_PATH = os.getenv("NIYAN_CONFIG_PATH", "/niyan/niyan.yaml")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_CONFIG_JSON = "niyan:config:json"
REDIS_CONFIG_VERSION = "niyan:config:version"

_cache: Dict[str, Any] = {"token": None, "data": None}
_redis = None
_redis_tried = False


def _client():
    global _redis, _redis_tried
    if _redis_tried:
        return _redis
    _redis_tried = True
    try:
        import redis  # type: ignore

        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True,
            socket_connect_timeout=0.5,
        )
        client.ping()
        _redis = client
    except Exception:
        _redis = None
    return _redis


def _token() -> str:
    client = _client()
    if client is not None:
        try:
            version = client.get(REDIS_CONFIG_VERSION)
            if version:
                return f"redis:{version}"
        except Exception:
            pass
    try:
        return f"file:{os.stat(NIYAN_CONFIG_PATH).st_mtime}"
    except OSError:
        return "missing"


def _from_file() -> Optional[Dict[str, Any]]:
    try:
        import yaml

        with open(NIYAN_CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return None


def load() -> Optional[Dict[str, Any]]:
    token = _token()
    if _cache["token"] == token:
        return _cache["data"]
    data = None
    client = _client()
    if client is not None:
        try:
            raw = client.get(REDIS_CONFIG_JSON)
            if raw:
                data = json.loads(raw)
        except Exception:
            data = None
    if data is None:
        data = _from_file()
    _cache["token"] = token
    _cache["data"] = data
    return data
