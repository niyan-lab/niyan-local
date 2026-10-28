"""Failed-login limiter for POST /api/auth/login.

Sliding window, in memory. The on-prem API runs as a single replica, so a
process-local store is enough and needs no Redis round-trip; counters reset
when the API restarts. (If the API is ever scaled out, move this to Redis.)

Key = (client IP, username). After MAX_FAILURES failed attempts inside
WINDOW_SECONDS the next attempt gets 429 with Retry-After until the oldest
failure leaves the window. A successful login clears the key.

Client IP: request.client.host by default. X-Forwarded-For is honoured only
when the direct peer is listed in NIYAN_TRUSTED_PROXIES (comma-separated IPs
or CIDRs, e.g. the admin-ui nginx). Otherwise anyone could spoof the header to
dodge the limit. Behind nginx without that setting, all browser clients share
nginx's IP, so the limit is effectively per username — acceptable for a
single-admin console.
"""

from __future__ import annotations

import ipaddress
import math
import os
import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, Optional, Tuple

MAX_FAILURES = 5
WINDOW_SECONDS = 60.0
_MAX_KEYS = 10_000


def _trusted_networks(raw: Optional[str] = None):
    raw = os.environ.get("NIYAN_TRUSTED_PROXIES", "") if raw is None else raw
    nets = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            continue
    return nets


def client_ip(peer: Optional[str], forwarded_for: Optional[str], trusted: Optional[str] = None) -> str:
    peer = peer or "unknown"
    if not forwarded_for:
        return peer
    try:
        peer_addr = ipaddress.ip_address(peer)
    except ValueError:
        return peer
    if not any(peer_addr in n for n in _trusted_networks(trusted)):
        return peer
    # Right-most entry is what the trusted proxy saw; earlier ones are client-supplied.
    hops = [h.strip() for h in forwarded_for.split(",") if h.strip()]
    return hops[-1] if hops else peer


class LoginLimiter:
    def __init__(self, max_failures: int = MAX_FAILURES, window: float = WINDOW_SECONDS,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.max_failures = max_failures
        self.window = window
        self.clock = clock
        self._fails: Dict[Tuple[str, str], Deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key, now) -> Deque[float]:
        q = self._fails.get(key)
        if q is None:
            return deque()
        while q and now - q[0] >= self.window:
            q.popleft()
        if not q:
            self._fails.pop(key, None)
        return q

    def retry_after(self, ip: str, username: str) -> int:
        """Seconds to wait if blocked, else 0."""
        key = (ip, username)
        with self._lock:
            now = self.clock()
            q = self._prune(key, now)
            if len(q) < self.max_failures:
                return 0
            return max(1, math.ceil(self.window - (now - q[0])))

    def record_failure(self, ip: str, username: str) -> None:
        key = (ip, username)
        with self._lock:
            now = self.clock()
            self._prune(key, now)
            if key not in self._fails and len(self._fails) >= _MAX_KEYS:
                self._fails.pop(next(iter(self._fails)))
            self._fails.setdefault(key, deque()).append(now)

    def reset(self, ip: str, username: str) -> None:
        with self._lock:
            self._fails.pop((ip, username), None)

    def clear(self) -> None:
        with self._lock:
            self._fails.clear()


limiter = LoginLimiter()
