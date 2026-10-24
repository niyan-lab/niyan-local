#!/usr/bin/env bash
# Basic RAG flow smoke test:
#   embed text → store in a test collection → retrieve via vector search
#
# Prerequisites:
#   - Stack up: niyan up
#   - Embedding model pulled: niyan embeddings pull
#   - Vector store enabled: niyan vector provider qdrant   # or pgvector
#
# Usage:
#   ./scripts/rag_smoke_test.sh
#
set -euo pipefail

PROXY_URL="${PROXY_URL:-http://127.0.0.1:4000}"
API_URL="${API_URL:-http://127.0.0.1:8100}"
API_KEY="${API_KEY:-$(niyan gateway keys --plain 2>/dev/null | head -1)}"
if [ -z "$API_KEY" ]; then echo "API_KEY empty: export API_KEY or run ./install.sh (niyan gateway keys --plain)" >&2; exit 1; fi
EMBED_MODEL="${EMBED_MODEL:-nomic-embed-text}"
EMBED_DIMS="${EMBED_DIMS:-768}"
ADMIN_USER="${ADMIN_USER:-$(niyan secrets show --field username 2>/dev/null || echo admin)}"
ADMIN_PASS="${ADMIN_PASS:-$(niyan secrets show --field password 2>/dev/null)}"
if [ -z "$ADMIN_PASS" ]; then echo "ADMIN_PASS empty: export ADMIN_PASS or run ./install.sh (niyan secrets show)" >&2; exit 1; fi
COLLECTION="${COLLECTION:-rag_smoke}"
DOC_ID="${DOC_ID:-rag-doc-1}"
DOC_TEXT="${DOC_TEXT:-Niyan is an Anaconda-style SLM stack with local embeddings and a vector database for RAG.}"
QUERY_TEXT="${QUERY_TEXT:-What is Niyan used for with embeddings and vectors?}"
TMP="${TMPDIR:-/tmp}/niyan-rag"
mkdir -p "$TMP"

red() { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
step() { printf '\n==> %s\n' "$*"; }

fail() {
  red "FAIL: $*"
  exit 1
}

step "1/6 Gateway health"
curl -sf "$PROXY_URL/health" >"$TMP/health.json" \
  || fail "gateway not reachable at $PROXY_URL — run niyan up"
green "gateway ok"

step "2/6 Admin login"
TOKEN=$(curl -sf "$API_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PASS\"}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])') \
  || fail "niyan-api login failed at $API_URL"
green "got admin token"

auth() {
  curl -sf "$@" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json"
}

step "3/6 Vector store health"
auth "$API_URL/api/vector/health" | tee "$TMP/vector-health.json"
echo
python3 -c '
import json,sys
h=json.load(open(sys.argv[1]))
sys.exit(0 if h.get("ok") else 1)
' "$TMP/vector-health.json" \
  || fail "vector store not healthy — enable with: niyan vector provider qdrant"
green "vector store ok ($(python3 -c 'import json; print(json.load(open("'"$TMP/vector-health.json"'")).get("provider"))'))"

step "4/6 Create collection '$COLLECTION' (dims=$EMBED_DIMS)"
curl -s -o /dev/null -X DELETE \
  "$API_URL/api/vector/collections/$COLLECTION" \
  -H "Authorization: Bearer $TOKEN" || true

auth -X POST "$API_URL/api/vector/collections" \
  -d "{\"name\":\"$COLLECTION\",\"size\":$EMBED_DIMS}" \
  | tee "$TMP/collection.json"
echo
green "collection ready"

step "5/6 Embed document + query ($EMBED_MODEL)"
embed_one() {
  # shellcheck disable=SC2034 # label kept for call-site readability
  local label="$1"
  local text="$2"
  local out="$3"
  PROXY_URL="$PROXY_URL" API_KEY="$API_KEY" EMBED_MODEL="$EMBED_MODEL" \
  TEXT="$text" OUT="$out" python3 - <<'PY'
import json, os, urllib.request, sys

req = urllib.request.Request(
    f"{os.environ['PROXY_URL'].rstrip('/')}/v1/embeddings",
    data=json.dumps({
        "model": os.environ["EMBED_MODEL"],
        "input": os.environ["TEXT"],
    }).encode(),
    headers={
        "Authorization": f"Bearer {os.environ['API_KEY']}",
        "Content-Type": "application/json",
    },
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.load(resp)
except Exception as exc:
    print(exc, file=sys.stderr)
    sys.exit(1)

open(os.environ["OUT"], "w").write(json.dumps(body))
vec = body["data"][0]["embedding"]
open(os.environ["OUT"] + ".vec", "w").write(json.dumps(vec))
print(len(vec))
PY
}

DOC_DIMS=$(embed_one "doc" "$DOC_TEXT" "$TMP/doc-embed.json") \
  || fail "doc embedding failed — pull model: niyan embeddings pull (or: niyan model pull $EMBED_MODEL)"
QUERY_DIMS=$(embed_one "query" "$QUERY_TEXT" "$TMP/query-embed.json") \
  || fail "query embedding failed"
[[ "$DOC_DIMS" -eq "$EMBED_DIMS" ]] || fail "expected $EMBED_DIMS dims, got $DOC_DIMS"
green "doc dims=$DOC_DIMS  query dims=$QUERY_DIMS"

step "6/6 Upsert document, then search with query embedding"
API_URL="$API_URL" TOKEN="$TOKEN" COLLECTION="$COLLECTION" DOC_ID="$DOC_ID" \
DOC_TEXT="$DOC_TEXT" DOC_VEC_FILE="$TMP/doc-embed.json.vec" \
QUERY_VEC_FILE="$TMP/query-embed.json.vec" \
UPSERT_OUT="$TMP/upsert.json" SEARCH_OUT="$TMP/search.json" \
python3 - <<'PY'
import json, os, urllib.request, sys

def post(path, payload, out):
    req = urllib.request.Request(
        f"{os.environ['API_URL'].rstrip('/')}{path}",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['TOKEN']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.load(resp)
    open(out, "w").write(json.dumps(body, indent=2))
    print(json.dumps(body, indent=2))
    return body

doc_vec = json.load(open(os.environ["DOC_VEC_FILE"]))
query_vec = json.load(open(os.environ["QUERY_VEC_FILE"]))

print("--- upsert ---")
post(
    "/api/vector/upsert",
    {
        "collection": os.environ["COLLECTION"],
        "points": [
            {
                "id": os.environ["DOC_ID"],
                "vector": doc_vec,
                "payload": {
                    "text": os.environ["DOC_TEXT"],
                    "source": "rag_smoke_test",
                    "flow": "embed-store-retrieve",
                },
            }
        ],
    },
    os.environ["UPSERT_OUT"],
)

print("--- search ---")
result = post(
    "/api/vector/search",
    {
        "collection": os.environ["COLLECTION"],
        "vector": query_vec,
        "limit": 3,
    },
    os.environ["SEARCH_OUT"],
)

hits = result.get("hits") or []
if not hits:
    print("no hits returned", file=sys.stderr)
    sys.exit(1)

top = hits[0]
print(f"top hit id={top.get('id')!r} score={top.get('score')}")
print(f"payload={top.get('payload')}")

if top.get("id") != os.environ["DOC_ID"]:
    print(f"expected top id {os.environ['DOC_ID']!r}, got {top.get('id')!r}", file=sys.stderr)
    sys.exit(1)

score = top.get("score")
if score is None or float(score) < 0.3:
    print(f"score too low for a related query: {score}", file=sys.stderr)
    sys.exit(1)
PY

green "RAG flow passed: embed → store ($COLLECTION/$DOC_ID) → retrieve"
echo
echo "Artifacts under $TMP/"
ls -1 "$TMP"
