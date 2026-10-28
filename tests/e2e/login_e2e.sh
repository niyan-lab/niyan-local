#!/usr/bin/env bash
# End-to-end login through the admin-ui nginx (/api proxy) to niyan-api.
# Asserts: right creds -> 200 + token, wrong -> 401, 6th failure in 60s -> 429.
# Isolated compose project + port (E2E_PROJECT, E2E_UI_PORT); tears down only
# what it created. Secrets are random per run and never printed.
set -euo pipefail
cd "$(dirname "$0")"
export E2E_PROJECT="${E2E_PROJECT:-niyan-login-e2e}"
export E2E_UI_PORT="${E2E_UI_PORT:-13080}"
# Build with the docker driver, not whatever buildx builder is currently selected.
# (The docker-driver builder is named after the active context.)
export BUILDX_BUILDER="${BUILDX_BUILDER:-$(docker context show)}"
rnd() { openssl rand -hex 16; }
E2E_ADMIN_PASSWORD="$(rnd)"; E2E_JWT_SECRET="$(rnd)$(rnd)"; E2E_LITELLM_KEY="sk-$(rnd)"
export E2E_ADMIN_PASSWORD E2E_JWT_SECRET E2E_LITELLM_KEY
DC=(docker compose -p "$E2E_PROJECT" -f docker-compose.login.yml)
cleanup() { "${DC[@]}" down -v --rmi local --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT

"${DC[@]}" up -d --build --wait
BASE="http://127.0.0.1:${E2E_UI_PORT}"
for _ in $(seq 1 60); do curl -fsS "$BASE/api/health" >/dev/null 2>&1 && break; sleep 1; done

post() {  # post <password> -> prints HTTP status
  curl -s -o /tmp/niyan-e2e-body.$$ -D /tmp/niyan-e2e-hdr.$$ -w '%{http_code}' \
    -H 'Content-Type: application/json' -X POST "$BASE/api/auth/login" \
    --data "{\"username\":\"admin\",\"password\":\"$1\"}"
}
fail() { echo "FAIL: $*" >&2; exit 1; }

s=$(post "$E2E_ADMIN_PASSWORD"); [ "$s" = 200 ] || fail "good login -> $s"
grep -q access_token /tmp/niyan-e2e-body.$$ || fail "no access_token"
echo "ok: good creds -> 200"
for i in 1 2 3 4 5; do s=$(post "wrong-$i"); [ "$s" = 401 ] || fail "bad login $i -> $s"; done
echo "ok: 5 wrong -> 401"
s=$(post "wrong-6"); [ "$s" = 429 ] || fail "6th bad login -> $s"
grep -qi '^retry-after:' /tmp/niyan-e2e-hdr.$$ || fail "429 without Retry-After"
echo "ok: 6th wrong -> 429 + Retry-After"
rm -f /tmp/niyan-e2e-body.$$ /tmp/niyan-e2e-hdr.$$
echo "PASS: login e2e via admin-ui nginx"
