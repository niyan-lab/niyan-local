#!/usr/bin/env bash
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec "$ROOT/.venv/bin/niyan" "$@"
