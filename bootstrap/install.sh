#!/usr/bin/env bash
# Anaconda-style remote installer for Niyan (pull-only).
# Materializes ~/.niyan, installs a thin `niyan` CLI, and can pull images.
#
# From a cloned repo (dev smoke of the pull-only path):
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

# Secret-bearing files are created owner-only; caller's umask restored below.
OLD_UMASK="$(umask)"
umask 077

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

# Per-install secrets (bash 3.2 + BSD/LibreSSL openssl compatible). Only fills
# empty or shipped-default values; never regenerates over real ones. Upgrades
# of old default installs are migrated in place (see README "Upgrading").
require_cmd openssl
is_insecure() {
  case "$1" in
    ""|niyan|sk-niyan-local|x|'***'|'********'|*change-me*|*changeme*|__*__|'<'*'>'|0000000000000000000000000000000000000000000000000000000000000000) return 0 ;;
  esac
  return 1
}
env_get() { grep -E "^$1=" "$STACK/.env" 2>/dev/null | head -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' || true; }
legacy_marker() {
  case "$1" in
    LANGFUSE_SALT) echo NIYAN_LEGACY_LANGFUSE_SALT ;;
    LANGFUSE_ENCRYPTION_KEY) echo NIYAN_LEGACY_LANGFUSE_ENCRYPTION_KEY ;;
    *) echo "" ;;
  esac
}
old_default() {
  case "$1" in
    POSTGRES_PASSWORD) echo niyan ;;
    LANGFUSE_SALT) echo niyan-langfuse-salt-change-me ;;
    LANGFUSE_ENCRYPTION_KEY) echo 0000000000000000000000000000000000000000000000000000000000000000 ;;
  esac
}
needs_work() {  # $1 = key
  local cur m
  cur="$(env_get "$1")"
  m="$(legacy_marker "$1")"
  if [[ -n "$m" && "$(env_get "$m")" == "1" && -n "$cur" ]]; then return 1; fi
  is_insecure "$cur"
}

DATA_KEYS=()
for key in POSTGRES_PASSWORD LANGFUSE_SALT LANGFUSE_ENCRYPTION_KEY; do
  if needs_work "$key"; then DATA_KEYS+=("$key"); fi
done
PG_VOLUME=0
if [[ ${#DATA_KEYS[@]} -gt 0 ]]; then
  # Fail closed: without Docker we cannot tell whether data exists.
  docker info >/dev/null 2>&1 || die "Docker is not reachable, so it is unknown whether Niyan's Postgres volume exists. Refusing to generate data-bound secrets (${DATA_KEYS[*]}). Start Docker and re-run. Nothing was changed."
  if docker volume inspect niyan_niyan_pg >/dev/null 2>&1; then PG_VOLUME=1; fi
fi

pg_compose() {
  (
    set -a
    # shellcheck disable=SC1091
    . "$STACK/.env"
    set +a
    for v in POSTGRES_PASSWORD LANGFUSE_NEXTAUTH_SECRET LANGFUSE_SALT LANGFUSE_ENCRYPTION_KEY \
      LITELLM_MASTER_KEY NIYAN_ADMIN_PASSWORD NIYAN_JWT_SECRET; do
      if [[ -z "${!v:-}" ]]; then export "$v=__niyan_unused__"; fi
    done
    export NIYAN_ROOT="$STACK" COMPOSE_PROJECT_NAME=niyan
    cd "$STACK" && docker compose --project-name niyan -f "$STACK/docker-compose.yml" "$@"
  )
}
PG_USER="$(env_get POSTGRES_USER)"; PG_USER="${PG_USER:-niyan}"
pg_sql() {  # $1 db, SQL on stdin; local socket inside the container (trust)
  pg_compose exec -T postgres psql -v ON_ERROR_STOP=1 -qtA -U "$PG_USER" -d "$1"
}
langfuse_rows() {  # $@ tables -> prints count (to_regclass-guarded)
  local parts="" t
  for t in "$@"; do
    [[ -n "$parts" ]] && parts="$parts + "
    parts="${parts}(case when to_regclass('public.$t') is null then 0 else (xpath('/row/c/text()', query_to_xml('select count(*) as c from public.$t', false, true, '')))[1]::text::int end)"
  done
  local db; db="$(env_get POSTGRES_DB)"
  echo "select $parts;" | pg_sql "${db:-langfuse}" 2>/dev/null | tail -1
}

if [[ "$PG_VOLUME" == "1" ]]; then
  echo "==> Existing Niyan Postgres volume found: migrating default secrets in place (data kept)"
  pg_compose up -d --no-deps postgres >/dev/null
  ready=0
  for _ in $(seq 1 60); do
    if echo "select 1;" | pg_sql postgres >/dev/null 2>&1; then ready=1; break; fi
    sleep 2
  done
  [[ "$ready" == "1" ]] || die "postgres did not become ready for migration (nothing rotated)"
  for key in "${DATA_KEYS[@]}"; do
    case "$key" in
      POSTGRES_PASSWORD)
        newpw="$(openssl rand -hex 24)"
        printf 'ALTER USER "%s" WITH PASSWORD '"'"'%s'"'"';\n' "$PG_USER" "$newpw" | pg_sql postgres >/dev/null \
          || die "ALTER USER failed; .env unchanged"
        printf '%s\n' "$newpw" | pg_compose exec -T postgres sh -c \
          'read -r P; H="$(hostname -i | cut -d" " -f1)"; PGPASSWORD="$P" psql -h "$H" -U "$0" -d postgres -qtAc "select 1"' "$PG_USER" >/dev/null \
          || die "new Postgres password did not verify over TCP"
        upsert_env POSTGRES_PASSWORD "$newpw" "$STACK/.env"
        echo "    rotated POSTGRES_PASSWORD (ALTER USER)"
        ;;
      LANGFUSE_SALT|LANGFUSE_ENCRYPTION_KEY)
        if [[ "$key" == LANGFUSE_SALT ]]; then n="$(langfuse_rows api_keys)"; else n="$(langfuse_rows llm_api_keys blob_storage_integrations posthog_integrations)"; fi
        if [[ "$n" == "0" ]]; then
          upsert_env "$key" "$(openssl rand -hex 32)" "$STACK/.env"
          echo "    rotated $key (no dependent Langfuse rows)"
        else
          cur="$(env_get "$key")"; [[ -n "$cur" ]] || cur="$(old_default "$key")"
          upsert_env "$key" "$cur" "$STACK/.env"
          upsert_env "$(legacy_marker "$key")" 1 "$STACK/.env"
          echo "    WARNING: kept old default $key: existing Langfuse data depends on it (${n:-unknown} rows)." >&2
          echo "             Anyone with repo access knows it. To rotate: export Langfuse data, then" >&2
          echo "             niyan uninstall --volumes and reinstall." >&2
        fi
        ;;
    esac
  done
fi

GENERATED_ADMIN=0
for key in NIYAN_ADMIN_PASSWORD NIYAN_JWT_SECRET LITELLM_MASTER_KEY POSTGRES_PASSWORD \
           LANGFUSE_NEXTAUTH_SECRET LANGFUSE_SALT LANGFUSE_ENCRYPTION_KEY; do
  needs_work "$key" || continue
  case "$key" in
    LITELLM_MASTER_KEY) val="sk-niyan-$(openssl rand -hex 24)" ;;
    # 24 chars, same length as the source CLI's generated admin password
    NIYAN_ADMIN_PASSWORD) val="$(openssl rand -hex 12)"; GENERATED_ADMIN=1 ;;
    *) val="$(openssl rand -hex 32)" ;;
  esac
  upsert_env "$key" "$val" "$STACK/.env"
done
chmod 600 "$STACK/.env"
if [[ -f "$STACK/niyan.yaml" ]]; then chmod 600 "$STACK/niyan.yaml"; fi
umask "$OLD_UMASK"

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
if [ "$GENERATED_ADMIN" = "1" ]; then
  echo "            login: admin / $(grep -E '^NIYAN_ADMIN_PASSWORD=' "$STACK/.env" | cut -d= -f2-)  (stored in $STACK/.env; now in your scrollback — clear it on shared screens)"
else
  echo "            login: admin / see NIYAN_ADMIN_PASSWORD in $STACK/.env"
fi
echo "  Gateway:  http://127.0.0.1:4000"
echo
echo "  Stop:       niyan down"
echo "  Uninstall:  niyan uninstall            # keep Docker volumes"
echo "              niyan uninstall --volumes  # also delete volumes"
echo
