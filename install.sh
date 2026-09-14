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
cp -n "$ROOT/.env.example" "$ROOT/.env" 2>/dev/null || true
cp -n "$ROOT/configs/niyan.example.yaml" "$ROOT/niyan.yaml" 2>/dev/null || true
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
echo "    niyan up"
echo "    niyan status"
echo
echo "  Undo shell wire-up:  niyan shell init --reverse"
echo "  Repo-local fallback: ./niyan.sh <command>"
echo
echo "Next steps:"
echo "  1) Install & start Ollama on the host (Mac/Windows: https://ollama.com),"
echo "     then: niyan model pull llama3.2:3b && niyan embeddings pull"
echo "     (Linux: Ollama runs in Compose; still use niyan model pull)"
echo "  Windows users: run .\\install.ps1 instead of this script"
echo "  2) niyan doctor"
echo "  3) niyan up"
echo "  4) curl OpenAI endpoint on :4000 (see docs/quickstart.md)"
