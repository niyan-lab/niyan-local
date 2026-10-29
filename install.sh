#!/usr/bin/env bash
# Niyan bootstrap — install CLI into a local venv and wire a Conda-style shell hook
# so `niyan` works from any directory (not just via ./niyan.sh in the repo).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "==> Niyan installer"
echo "Repo: $ROOT"

if ! command -v python3 >/dev/null; then
  echo "python3 is required" >&2
  exit 1
fi

if ! command -v docker >/dev/null; then
  echo "Docker is required" >&2
  exit 1
fi

python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/pip" install -U pip setuptools wheel --quiet
"$ROOT/.venv/bin/pip" install -e "$ROOT/cli" --quiet
OLD_UMASK="$(umask)"
umask 077
[ -f "$ROOT/.env" ] || cp "$ROOT/.env.example" "$ROOT/.env"
[ -f "$ROOT/niyan.yaml" ] || cp "$ROOT/configs/niyan.example.yaml" "$ROOT/niyan.yaml"
umask "$OLD_UMASK"
# Secrets: generate / migrate in place. Fails closed (exit 2, nothing changed)
# when Docker is unreachable and a data-bound secret would need work.
set +e
SECRETS_JSON="$(NIYAN_ROOT="$ROOT" "$ROOT/.venv/bin/niyan" secrets init --json)"
SECRETS_RC=$?
set -e
NEW_ADMIN_PW="$(printf '%s' "$SECRETS_JSON" | "$ROOT/.venv/bin/python" -c '
import json, sys
try:
    r = json.loads(sys.stdin.read().strip().splitlines()[-1])
except Exception:
    print("error: could not parse `niyan secrets init --json` output", file=sys.stderr); sys.exit(3)
if not r.get("ok"):
    print("error: " + r.get("error", "secrets init failed"), file=sys.stderr); sys.exit(2)
for k in ("rotated", "generated", "kept"):
    if r.get(k):
        print("  %s: %s" % (k, ", ".join(r[k])), file=sys.stderr)
for w in r.get("warnings", []):
    print("  WARNING: " + w, file=sys.stderr)
print("1" if "admin_auth.password" in r.get("generated", []) else "0")
')" || { echo "Install aborted: secrets were not changed." >&2; exit 2; }
if [ "$SECRETS_RC" -ne 0 ]; then
  echo "Install aborted (niyan secrets init exit $SECRETS_RC)." >&2
  exit "$SECRETS_RC"
fi
# Generate LiteLLM routes from niyan.yaml (required Compose mount)
"$ROOT/.venv/bin/python" - <<PY
from pathlib import Path
from niyan.config import load_config
from niyan.litellm_gen import generate_litellm_config
root = Path("$ROOT")
cfg = load_config(root / "niyan.yaml")
generate_litellm_config(cfg, root)
print("LiteLLM config generated")
PY

# Thin repo wrapper kept for scripts / CI that still call ./niyan.sh
cat > "$ROOT/niyan.sh" <<'EOF'
#!/usr/bin/env bash
ROOT="$(cd "$(dirname "$0")" && pwd)"
export NIYAN_ROOT="$ROOT"
exec "$ROOT/.venv/bin/niyan" "$@"
EOF
chmod +x "$ROOT/niyan.sh"
chmod +x "$ROOT/shell/niyan.sh" 2>/dev/null || true

# Conda-style: export NIYAN_ROOT + put .venv/bin on PATH via ~/.zshrc or ~/.bashrc
export NIYAN_ROOT="$ROOT"
if ! "$ROOT/.venv/bin/niyan" shell init; then
  echo "warning: could not update shell profile (permission denied?)" >&2
  echo "  Fix: sudo chown \"\$(whoami)\" ~/.zshrc   # if owned by root" >&2
  echo "  Or use repo-local CLI: ./niyan.sh doctor && ./niyan.sh up --build" >&2
fi

echo
echo "Installed."
echo
echo "  Like conda: open a new terminal (or: source your ~/.zshrc / ~/.bashrc),"
echo "  then use niyan from anywhere:"
echo
echo "    niyan doctor"
echo "    niyan up --build    # first start, and after every git pull / branch switch"
echo "    niyan status"
echo
if [ "$NEW_ADMIN_PW" = "1" ]; then
  echo "  Admin UI login (new password; stored in niyan.yaml, chmod 600; reprint any time"
  echo "  with: niyan secrets show). It is now in your terminal scrollback — clear it on shared screens:"
  NIYAN_ROOT="$ROOT" "$ROOT/.venv/bin/niyan" secrets show | sed 's/^/    /'
else
  echo "  Existing secrets kept. Show the admin login with: niyan secrets show"
fi
echo
echo "  Uninstall:           ./uninstall.sh"
echo "  Repo-local fallback: ./niyan.sh <command>"
echo
echo "Next steps:"
echo "  1) Mac/Windows: install & start Ollama (https://ollama.com)"
echo "  2) source ~/.zshrc   # or ~/.bashrc, then:"
echo "  3) niyan doctor"
echo "  4) niyan up --build   # first start, and after every git pull / branch switch"
echo "  5) see README.md"
