#!/usr/bin/env bash
# End-to-end login through the admin-ui nginx (/api proxy) to niyan-api.
#   host:     right creds -> 200, wrong -> 401, 6th failure in 60s -> 429
#   client-a: locked out via nginx; a forged X-Forwarded-For does not help
#   client-b: different real IP behind the same nginx -> not locked out
#   direct:   forged X-Forwarded-For straight at the published API port is
#             ignored (peer is not the trusted admin-ui), so 6th -> 429
# Isolated compose project + ports (E2E_PROJECT, E2E_UI_PORT, E2E_API_PORT);
# tears down only what it created. Secrets are random and never printed.
set -euo pipefail
cd "$(dirname "$0")"
export E2E_PROJECT="${E2E_PROJECT:-niyan-login-e2e}"
export E2E_UI_PORT="${E2E_UI_PORT:-13080}"
export E2E_API_PORT="${E2E_API_PORT:-18100}"
# Build with the docker driver, not whatever buildx builder is currently selected.
# (The docker-driver builder is named after the active context.)
export BUILDX_BUILDER="${BUILDX_BUILDER:-$(docker context show)}"
rnd() { openssl rand -hex 16; }
E2E_ADMIN_PASSWORD="$(rnd)"; E2E_JWT_SECRET="$(rnd)$(rnd)"; E2E_LITELLM_KEY="sk-$(rnd)"
export E2E_ADMIN_PASSWORD E2E_JWT_SECRET E2E_LITELLM_KEY
DC=(docker compose -p "$E2E_PROJECT" -f docker-compose.login.yml)
HDR="$(mktemp)"
cleanup() { rm -f "$HDR"; "${DC[@]}" down -v --rmi local --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT

"${DC[@]}" up -d --build --wait
UI="http://127.0.0.1:${E2E_UI_PORT}"
API="http://127.0.0.1:${E2E_API_PORT}"
for _ in $(seq 1 60); do curl -fsS "$UI/api/health" >/dev/null 2>&1 && break; sleep 1; done

# login <from: host|client-a|client-b> <base-url> <password> [x-forwarded-for]
# prints the HTTP status; response headers go to $HDR (host only).
login() {
  local from=$1 url=$2/api/auth/login pw=$3 xff=${4:-}
  local args=(-s -o /dev/null -w '%{http_code}' -H 'Content-Type: application/json'
    -X POST "$url" --data "{\"username\":\"${LOGIN_USER:-admin}\",\"password\":\"$pw\"}")
  [ -n "$xff" ] && args+=(-H "X-Forwarded-For: $xff")
  if [ "$from" = host ]; then curl -D "$HDR" "${args[@]}"
  else "${DC[@]}" exec -T "$from" curl "${args[@]}"; fi
}
fail() { echo "FAIL: $*" >&2; exit 1; }
expect() { [ "$1" = "$2" ] || fail "$3 -> $1 (want $2)"; }

expect "$(login host "$UI" "$E2E_ADMIN_PASSWORD")" 200 "host good login"
echo "ok: good creds -> 200"
for i in 1 2 3 4 5; do expect "$(login host "$UI" "w$i")" 401 "host bad login $i"; done
expect "$(login host "$UI" w6)" 429 "host 6th bad login"
grep -qi '^retry-after:' "$HDR" || fail "429 without Retry-After"
echo "ok: 5 wrong -> 401, 6th -> 429 + Retry-After"

NGINX="http://admin-ui"
for i in 1 2 3 4 5; do expect "$(login client-a "$NGINX" "a$i")" 401 "client-a bad login $i"; done
expect "$(login client-a "$NGINX" a6)" 429 "client-a 6th"
expect "$(login client-a "$NGINX" a7 "203.0.113.9")" 429 "client-a with forged XFF via nginx"
echo "ok: client-a locked out; forged X-Forwarded-For via nginx does not reset it"
expect "$(login client-b "$NGINX" b1)" 401 "client-b (other IP) bad login"
expect "$(login client-b "$NGINX" "$E2E_ADMIN_PASSWORD")" 200 "client-b good login"
echo "ok: client-b (different real IP) not locked out"

# The host reaches nginx and the published API port from the same address, so
# use a fresh username bucket here.
for i in 1 2 3 4 5; do expect "$(LOGIN_USER=ops login host "$API" "d$i" "198.51.100.$i")" 401 "direct forged-XFF $i"; done
expect "$(LOGIN_USER=ops login host "$API" d6 "198.51.100.99")" 429 "direct forged-XFF 6th"
expect "$(login client-b "http://niyan-api:8100" "$E2E_ADMIN_PASSWORD" "203.0.113.50")" 200 "client-b direct"
echo "ok: forged X-Forwarded-For straight to the API port is ignored"
echo "PASS: login e2e via admin-ui nginx"
