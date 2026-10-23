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
if [[ -x "$NIYAN" ]]; then
  args=(uninstall --yes)
  [[ "$VOLUMES" == "1" ]] && args+=(--volumes)
  [[ "$KEEP_CONFIG" == "1" ]] && args+=(--keep-config)
  if "$NIYAN" "${args[@]}"; then
    exit 0
  fi
  echo "CLI failed — falling back to manual cleanup"
fi

[[ ! -x "$NIYAN" ]] && echo "CLI venv missing — falling back to Compose + shell cleanup"

if command -v docker >/dev/null 2>&1 && [[ -f "$ROOT/deploy/docker-compose.yml" ]]; then
  compose=(docker compose --project-name niyan -f "$ROOT/deploy/docker-compose.yml")
  [[ -f "$ROOT/deploy/docker-compose.host-ollama.yml" ]] && \
    compose+=(-f "$ROOT/deploy/docker-compose.host-ollama.yml")
  # Include all profiles to ensure all volumes are removed when --volumes is used
  compose+=(--profile ollama --profile obs --profile guard-llm --profile guard-nemo --profile admin --profile vector-qdrant)
  down_args=(down --remove-orphans)
  [[ "$VOLUMES" == "1" ]] && down_args+=(--volumes)
  "${compose[@]}" "${down_args[@]}" || true
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

echo "Uninstalled. Reinstall with ./install.sh"
