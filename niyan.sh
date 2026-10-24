#!/usr/bin/env bash
ROOT="$(cd "$(dirname "$0")" && pwd)"
export NIYAN_ROOT="$ROOT"
exec "$ROOT/.venv/bin/niyan" "$@"
