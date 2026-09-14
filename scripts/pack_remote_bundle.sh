#!/usr/bin/env bash
# Pack bootstrap/ into a tarball you can host for curl|bash installs.
# Usage:
#   ./scripts/pack_remote_bundle.sh
#   ./scripts/pack_remote_bundle.sh 0.1.0
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAG="${1:-${NIYAN_IMAGE_TAG:-0.1.0}}"
OUT_DIR="${NIYAN_BUNDLE_OUT:-$ROOT/dist}"
NAME="niyan-bundle-${TAG}"
STAGE="$OUT_DIR/$NAME"

# Refresh release compose into bootstrap stack from monorepo deploy/
cp "$ROOT/deploy/docker-compose.release.yml" "$ROOT/bootstrap/stack/docker-compose.yml"
cp "$ROOT/deploy/docker-compose.host-ollama.yml" "$ROOT/bootstrap/stack/docker-compose.host-ollama.yml"

# Stamp default tag in .env.example
if grep -q '^NIYAN_IMAGE_TAG=' "$ROOT/bootstrap/stack/.env.example"; then
  tmp="$(mktemp)"
  awk -v v="$TAG" 'BEGIN{FS=OFS="="} $1=="NIYAN_IMAGE_TAG"{$2=v} {print}' \
    "$ROOT/bootstrap/stack/.env.example" >"$tmp"
  mv "$tmp" "$ROOT/bootstrap/stack/.env.example"
fi

rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "$ROOT/bootstrap/bin" "$STAGE/"
cp -R "$ROOT/bootstrap/stack" "$STAGE/"
# Include install.sh inside the tarball for reinstalls
cp "$ROOT/bootstrap/install.sh" "$STAGE/install.sh"
chmod +x "$STAGE/bin/niyan" "$STAGE/install.sh"

mkdir -p "$OUT_DIR"
TAR="$OUT_DIR/${NAME}.tgz"
tar -czf "$TAR" -C "$OUT_DIR" "$NAME"
rm -rf "$STAGE"

echo "Wrote $TAR"
echo "Host this file privately, then testers run:"
echo "  export NIYAN_BUNDLE_URL='https://…/${NAME}.tgz'"
echo "  curl -fsSL https://…/install.sh | bash"
echo "(publish bootstrap/install.sh as the curl target; it honors NIYAN_BUNDLE_URL)"
