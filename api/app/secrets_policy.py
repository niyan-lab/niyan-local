"""Shared secret deny-list (vendored copy; keep identical in all three places).

cli/niyan/secrets_policy.py == api/app/secrets_policy.py == services/gateway/secrets_policy.py
(enforced by cli/tests/test_secrets_policy_sync.py).
"""

from __future__ import annotations

import hmac
import os
import re
import sys
from typing import Iterable, List
from urllib.parse import urlparse

# Values that shipped as defaults in earlier builds. Always treated as "unset".
INSECURE_VALUES = frozenset(
    {
        "",
        "niyan",
        "sk-niyan-local",
        "change-me-niyan-dev-secret",
        "niyan-langfuse-nextauth-secret-change-me",
        "niyan-langfuse-salt-change-me",
        "0" * 64,
        "x",
        "***",
        "********",
    }
)
PLACEHOLDER_RE = re.compile(r"^(__.*__|<.*>|change-?me.*|\*+)$", re.I)
ALLOW_ENV = "NIYAN_ALLOW_INSECURE_DEFAULTS"
MASK = "********"


def is_insecure(value) -> bool:
    v = str(value or "").strip().strip("\"'")
    return v in INSECURE_VALUES or bool(PLACEHOLDER_RE.match(v)) or "change-me" in v.lower()


def dsn_password_insecure(dsn: str) -> bool:
    """True if a postgres DSN carries an empty/default password (empty DSN -> False)."""
    if not (dsn or "").strip():
        return False
    try:
        return is_insecure(urlparse(dsn).password or "")
    except Exception:
        return True


def insecure_allowed(env=None) -> bool:
    """Bypass only for the literal value "1" (dev/test only). Logs loudly when active."""
    env = os.environ if env is None else env
    if env.get(ALLOW_ENV, "") == "1":
        sys.stderr.write(
            "\n\033[1;31mWARNING: %s=1 — insecure/default secrets are ALLOWED. "
            "Never use this outside throwaway dev/tests.\033[0m\n\n" % ALLOW_ENV
        )
        return True
    return False


def bad_names(pairs: Iterable) -> List[str]:
    return [name for name, value in pairs if is_insecure(value)]


def ct_equal(a, b) -> bool:
    return hmac.compare_digest(str(a or "").encode("utf-8"), str(b or "").encode("utf-8"))


def ct_in(token, candidates: Iterable) -> bool:
    found = False
    for c in candidates:
        found |= ct_equal(token, c)
    return found
