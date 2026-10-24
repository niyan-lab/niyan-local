#!/usr/bin/env bash
# Smoke test against a running Niyan stack.
set -euo pipefail

PROXY_URL="${PROXY_URL:-http://127.0.0.1:4000}"
API_URL="${API_URL:-http://127.0.0.1:8100}"
API_KEY="${API_KEY:-$(niyan gateway keys --plain 2>/dev/null | head -1)}"
if [ -z "$API_KEY" ]; then echo "API_KEY empty: export API_KEY or run ./install.sh (niyan gateway keys --plain)" >&2; exit 1; fi
MODEL="${MODEL:-llama3.2:3b}"
EMBED_MODEL="${EMBED_MODEL:-nomic-embed-text}"
ADMIN_USER="${ADMIN_USER:-$(niyan secrets show --field username 2>/dev/null || echo admin)}"
ADMIN_PASS="${ADMIN_PASS:-$(niyan secrets show --field password 2>/dev/null)}"
if [ -z "$ADMIN_PASS" ]; then echo "ADMIN_PASS empty: export ADMIN_PASS or run ./install.sh (niyan secrets show)" >&2; exit 1; fi

echo "==> Health"
curl -sf "$PROXY_URL/health" | tee /tmp/niyan-health.json
echo

echo "==> Chat completion"
curl -sf "$PROXY_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Say one short story.\"}]}" \
  | tee /tmp/niyan-chat.json
echo

echo "==> PII / guardrails path (expect redact or allow with metadata)"
curl -s "$PROXY_URL/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"My SSN is 123-45-6789\"}]}" \
  | tee /tmp/niyan-pii.json
echo

echo "==> Embeddings ($EMBED_MODEL)"
if curl -sf "$PROXY_URL/v1/embeddings" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$EMBED_MODEL\",\"input\":\"Niyan vector smoke test\"}" \
  | tee /tmp/niyan-embed.json; then
  echo
else
  echo "(skipped/failed — pull with: niyan embeddings pull)"
fi

echo "==> Vector store (if enabled)"
if TOKEN=$(curl -sf "$API_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PASS\"}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])' 2>/dev/null); then
  if curl -sf "$API_URL/api/vector/health" -H "Authorization: Bearer $TOKEN" | tee /tmp/niyan-vector-health.json; then
    echo
    python3 - <<'PY' || true
import json
h = json.load(open("/tmp/niyan-vector-health.json"))
if not h.get("ok"):
    print("(vector store not healthy / disabled — enable with: niyan vector provider qdrant)")
    raise SystemExit(0)
emb = json.load(open("/tmp/niyan-embed.json"))
vec = emb["data"][0]["embedding"]
print(f"embedding dims={len(vec)}")
open("/tmp/niyan-embed-vec.json","w").write(json.dumps(vec))
PY
    if [[ -f /tmp/niyan-embed-vec.json ]]; then
      VEC=$(cat /tmp/niyan-embed-vec.json)
      curl -sf "$API_URL/api/vector/collections" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"name":"smoke","size":768}' >/tmp/niyan-vector-col.json || true
      curl -sf "$API_URL/api/vector/upsert" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"collection\":\"smoke\",\"points\":[{\"id\":\"doc-1\",\"vector\":$VEC,\"payload\":{\"text\":\"Niyan vector smoke test\"}}]}" \
        | tee /tmp/niyan-vector-upsert.json
      echo
      curl -sf "$API_URL/api/vector/search" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"collection\":\"smoke\",\"vector\":$VEC,\"limit\":3}" \
        | tee /tmp/niyan-vector-search.json
      echo
    fi
  else
    echo "(vector health failed — store may be disabled)"
  fi
else
  echo "(niyan-api login failed — skip vector checks)"
fi

echo "Smoke finished."
