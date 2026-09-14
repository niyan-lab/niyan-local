#!/usr/bin/env bash
# Anaconda-style remote installer for Niyan (pull-only).
# Materializes ~/.niyan, installs a thin `niyan` CLI, and can pull images.
#
# From a cloned repo (dev smoke):
#   ./install-remote.sh
#   ./bootstrap/install.sh
#
# From your website (testers):
#   export NIYAN_BUNDLE_URL='https://…/niyan-bundle-0.1.0.tgz'
#   curl -fsSL https://…/install.sh | bash
#
# Prerequisites: Docker + Compose v2; docker login to private GHCR (invite email).
set -euo pipefail

NIYAN_HOME="${NIYAN_HOME:-$HOME/.niyan}"
STACK="$NIYAN_HOME/stack"
BIN_DIR="$NIYAN_HOME/bin"
LOCAL_BIN="${NIYAN_LOCAL_BIN:-$HOME/.local/bin}"
IMAGE_TAG="${NIYAN_IMAGE_TAG:-0.1.0}"
IMAGE_REGISTRY="${NIYAN_IMAGE_REGISTRY:-ghcr.io/intelligentindia7}"
PULL_ON_INSTALL="${NIYAN_PULL_ON_INSTALL:-1}"
MARKER_BEGIN="# >>> niyan initialize >>>"
MARKER_END="# <<< niyan initialize <<<"

echo "==> Niyan remote installer"
echo "    Home: $NIYAN_HOME"

die() {
  echo "error: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "'$1' is required"
}

require_cmd docker
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required (docker compose)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# When this file is bootstrap/install.sh, SOURCE_ROOT is bootstrap/
# When invoked via repo-root install-remote.sh, BASH_SOURCE may be the wrapper.
if [[ -d "$SCRIPT_DIR/stack" && -f "$SCRIPT_DIR/bin/niyan" ]]; then
  BUNDLE_SRC="$SCRIPT_DIR"
elif [[ -d "$SCRIPT_DIR/bootstrap/stack" && -f "$SCRIPT_DIR/bootstrap/bin/niyan" ]]; then
  BUNDLE_SRC="$SCRIPT_DIR/bootstrap"
else
  BUNDLE_SRC=""
fi

materialize_from_dir() {
  local src="$1"
  echo "==> Installing stack from $src"
  mkdir -p "$BIN_DIR" "$STACK"
  cp -R "$src/stack/." "$STACK/"
  cp "$src/bin/niyan" "$BIN_DIR/niyan"
  chmod +x "$BIN_DIR/niyan"
}

materialize_from_url() {
  local url="$1"
  require_cmd curl
  require_cmd tar
  local tmp
  tmp="$(mktemp -d)"
  echo "==> Downloading bundle: $url"
  curl -fsSL "$url" -o "$tmp/bundle.tgz"
  mkdir -p "$tmp/extract"
  tar -xzf "$tmp/bundle.tgz" -C "$tmp/extract"
  # Tarball should contain bin/ and stack/ at top level (or one wrapper dir).
  if [[ -d "$tmp/extract/stack" && -f "$tmp/extract/bin/niyan" ]]; then
    materialize_from_dir "$tmp/extract"
  else
    local inner
    inner="$(find "$tmp/extract" -maxdepth 2 -type d -name stack | head -1)"
    [[ -n "$inner" ]] || die "bundle missing stack/ directory"
    local root
    root="$(cd "$(dirname "$inner")" && pwd)"
    [[ -f "$root/bin/niyan" ]] || die "bundle missing bin/niyan"
    materialize_from_dir "$root"
  fi
  rm -rf "$tmp"
}

if [[ -n "${NIYAN_BUNDLE_URL:-}" ]]; then
  materialize_from_url "$NIYAN_BUNDLE_URL"
elif [[ -n "$BUNDLE_SRC" ]]; then
  materialize_from_dir "$BUNDLE_SRC"
else
  die "No bundle source. Set NIYAN_BUNDLE_URL=… or run from a checkout that contains bootstrap/"
fi

# default niyan.yaml from example if pack omitted the gitignored name
if [[ ! -f "$STACK/niyan.yaml" && -f "$STACK/niyan.example.yaml" ]]; then
  cp "$STACK/niyan.example.yaml" "$STACK/niyan.yaml"
fi

# .env
if [[ ! -f "$STACK/.env" ]]; then
  if [[ -f "$STACK/.env.example" ]]; then
    cp "$STACK/.env.example" "$STACK/.env"
  else
    touch "$STACK/.env"
  fi
fi

# Stamp registry/tag into .env (idempotent-ish updates)
upsert_env() {
  local key="$1" val="$2" file="$3"
  if grep -qE "^${key}=" "$file" 2>/dev/null; then
    # portable-ish in-place replace
    local tmp
    tmp="$(mktemp)"
    awk -v k="$key" -v v="$val" 'BEGIN{FS=OFS="="} $1==k{$0=k"="v} {print}' "$file" >"$tmp"
    mv "$tmp" "$file"
  else
    printf '%s=%s\n' "$key" "$val" >>"$file"
  fi
}

upsert_env NIYAN_IMAGE_REGISTRY "$IMAGE_REGISTRY" "$STACK/.env"
upsert_env NIYAN_IMAGE_TAG "$IMAGE_TAG" "$STACK/.env"

# PATH: prefer ~/.niyan/bin; also try ~/.local/bin symlink
chmod +x "$BIN_DIR/niyan"
mkdir -p "$LOCAL_BIN" 2>/dev/null || true
if ln -sfn "$BIN_DIR/niyan" "$LOCAL_BIN/niyan" 2>/dev/null; then
  echo "==> Linked $LOCAL_BIN/niyan"
else
  echo "==> Note: could not link $LOCAL_BIN/niyan (using $BIN_DIR/niyan via shell PATH)"
fi

shell_rc() {
  case "$(basename "${SHELL:-bash}")" in
    zsh) echo "$HOME/.zshrc" ;;
    bash)
      if [[ -f "$HOME/.bashrc" ]]; then
        echo "$HOME/.bashrc"
      else
        echo "$HOME/.bash_profile"
      fi
      ;;
    *) echo "$HOME/.bashrc" ;;
  esac
}

RC="$(shell_rc)"
if touch "$RC" 2>/dev/null; then
  if ! grep -qF "$MARKER_BEGIN" "$RC" 2>/dev/null; then
    echo "==> Wiring PATH in $RC"
    {
      echo ""
      echo "$MARKER_BEGIN"
      echo "export NIYAN_HOME=\"$NIYAN_HOME\""
      echo "export NIYAN_ROOT=\"\$NIYAN_HOME/stack\""
      echo "export PATH=\"\$NIYAN_HOME/bin:\$HOME/.local/bin:\$PATH\""
      echo "$MARKER_END"
    } >>"$RC"
  else
    echo "==> Shell block already present in $RC"
  fi
else
  echo "==> Note: could not update $RC — add to PATH manually:"
  echo "    export PATH=\"$BIN_DIR:\$PATH\""
  RC="(none)"
fi

export NIYAN_HOME NIYAN_ROOT="$STACK" PATH="$BIN_DIR:$LOCAL_BIN:$PATH"

if [[ "$PULL_ON_INSTALL" == "1" ]]; then
  echo "==> Pulling images (public deps + private Niyan wrappers)"
  echo "    Ensure you already ran: docker login ghcr.io"
  if ! "$BIN_DIR/niyan" pull; then
    echo "warning: docker compose pull failed — check GHCR login / package visibility" >&2
  fi
fi

echo
echo "Installed."
echo
if [[ "$RC" != "(none)" ]]; then
  echo "  Open a new terminal (or: source $RC), then:"
else
  echo "  Ensure $BIN_DIR is on PATH, then:"
fi
echo
echo "    niyan doctor"
echo "    niyan up"
echo
echo "  Admin UI: http://127.0.0.1:3080"
echo "  Gateway:  http://127.0.0.1:4000"
echo
echo "  Stop:     niyan down"
if [[ "$RC" != "(none)" ]]; then
  echo "  Unwire:   remove the niyan block from $RC and rm -rf $NIYAN_HOME"
else
  echo "  Remove:   rm -rf $NIYAN_HOME"
fi
echo
