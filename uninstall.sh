#!/usr/bin/env bash
# Remove a from-source Niyan install (Compose stack, shell hook, venv).
# Does not delete this checkout.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

VOLUMES=0
KEEP_CONFIG=0
YES=0
for arg in "$@"; do
  case "$arg" in
    --volumes|-v) VOLUMES=1 ;;
    --keep-config) KEEP_CONFIG=1 ;;
    --yes|-y) YES=1 ;;
    -h|--help)
      cat <<'EOF'
Usage: ./uninstall.sh [--volumes] [--keep-config] [--yes]

  --volumes       Also delete Docker volumes (Postgres, Redis, …)
  --keep-config   Keep niyan.yaml and .env
  --yes           Do not prompt

This leaves the git checkout in place. Reinstall with ./install.sh
EOF
      exit 0
      ;;
    *)
      echo "unknown flag: $arg (try --help)" >&2
      exit 1
      ;;
  esac
done

echo "==> Niyan uninstall"
echo "Repo: $ROOT"

if [[ "$YES" != "1" ]]; then
  echo "This will stop Compose, unwire your shell, and delete .venv"
  if [[ "$VOLUMES" == "1" ]]; then
    echo "(Docker volumes will also be deleted.)"
  fi
  read -r -p "Continue? [y/N] " reply
  case "$reply" in
    y|Y|yes|YES) ;;
    *) echo "Aborted."; exit 1 ;;
  esac
fi

NIYAN="$ROOT/.venv/bin/niyan"
# NIYAN_UNINSTALL_SKIP_CLI=1 forces the fallback path (used by tests).
if [[ -x "$NIYAN" && "${NIYAN_UNINSTALL_SKIP_CLI:-0}" != "1" ]]; then
  args=(uninstall --yes)
  if [[ "$VOLUMES" == "1" ]]; then args+=(--volumes); fi
  if [[ "$KEEP_CONFIG" == "1" ]]; then args+=(--keep-config); fi
  cli_rc=0
  "$NIYAN" "${args[@]}" || cli_rc=$?
  if [[ "$cli_rc" == "0" ]]; then
    exit 0
  fi
  if [[ "$cli_rc" == "3" ]]; then
    # Compose could not stop the stack; the CLI removed nothing. Do not fall back.
    exit 3
  fi
  echo "CLI failed (exit $cli_rc) — falling back to manual cleanup" >&2
else
  echo "CLI venv missing (or skipped) — falling back to Compose + shell cleanup"
fi

FALLBACK_RC=0
if command -v docker >/dev/null 2>&1 && [[ -f "$ROOT/deploy/docker-compose.yml" ]]; then
  compose=(docker compose --project-name niyan -f "$ROOT/deploy/docker-compose.yml")
  if [[ -f "$ROOT/deploy/docker-compose.host-ollama.yml" ]]; then
    compose+=(-f "$ROOT/deploy/docker-compose.host-ollama.yml")
  fi
  if [[ -f "$ROOT/.env" ]]; then
    compose+=(--env-file "$ROOT/.env")
  fi
  # Every profile, so --volumes really removes every volume.
  compose+=(--profile ollama --profile obs --profile guard-llm --profile guard-nemo --profile admin \
    --profile vector-qdrant --profile vector-pg)
  # `down` still interpolates ${VAR:?} guards: give missing ones a dummy value
  # (only used for interpolation; nothing is started).
  for v in POSTGRES_PASSWORD LANGFUSE_NEXTAUTH_SECRET LANGFUSE_SALT LANGFUSE_ENCRYPTION_KEY \
    LITELLM_MASTER_KEY NIYAN_ADMIN_PASSWORD NIYAN_JWT_SECRET; do
    if [[ -z "${!v:-}" ]] && ! grep -Eq "^${v}=.+" "$ROOT/.env" 2>/dev/null; then
      export "$v=__niyan_unused__"
    fi
  done
  export NIYAN_ROOT="$ROOT"
  down_args=(down --remove-orphans)
  if [[ "$VOLUMES" == "1" ]]; then down_args+=(--volumes); fi
  if ! "${compose[@]}" "${down_args[@]}"; then
    echo "error: docker compose down failed (is Docker running?)." >&2
    echo "       Nothing was removed. Start Docker and re-run ./uninstall.sh." >&2
    exit 3
  fi
else
  echo "warning: docker not found — skipping container/volume cleanup" >&2
fi

python3 - "$ROOT" <<'PY'
import re
import sys
from pathlib import Path

begin, end = "# >>> niyan initialize >>>", "# <<< niyan initialize <<<"
pat = re.compile(re.escape(begin) + r".*?" + re.escape(end) + r"\n?", re.S)
home = Path.home()
for rc in (home / ".zshrc", home / ".bashrc", home / ".bash_profile"):
    if not rc.exists():
        continue
    text = rc.read_text(encoding="utf-8")
    if begin not in text:
        continue
    rc.write_text(re.sub(r"\n{3,}", "\n\n", pat.sub("", text)), encoding="utf-8")
    print(f"Removed Niyan block from {rc}")
PY

rm -rf "$ROOT/.venv"
if [[ "$KEEP_CONFIG" != "1" ]]; then
  rm -f "$ROOT/niyan.yaml" "$ROOT/.env"
fi
rm -f "$ROOT/services/litellm/config.generated.yaml"

if [[ "$FALLBACK_RC" != "0" ]]; then
  echo "Uninstall finished WITH ERRORS (see above)." >&2
  exit "$FALLBACK_RC"
fi
echo "Uninstalled. Reinstall with ./install.sh"
