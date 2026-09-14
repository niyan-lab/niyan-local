#!/usr/bin/env bash
# Repo-root entrypoint for the remote / pull-only installer.
# Delegates to bootstrap/install.sh (same UX as curl|bash for testers).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec "$ROOT/bootstrap/install.sh" "$@"
