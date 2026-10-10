"""Deployment platform for niyan-local: always Compose / VM."""

from __future__ import annotations

import os

VM = "vm"


def resolve_platform() -> str:
    """niyan-local supports Docker Compose only — always ``vm``.

    ``NIYAN_PLATFORM=kubernetes`` (and legacy ``NIYAN_ORCHESTRATOR``) are ignored;
    Kubernetes packaging lives in niyan-complete.
    """
    _ = os.getenv("NIYAN_PLATFORM")  # acknowledged but unused
    return VM
