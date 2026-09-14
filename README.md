# Niyan

**Anaconda-style SLM stack manager** — one config + CLI brings up Ollama-backed Llama/Gemma, **OpenAI / Gemini / Anthropic** (optional), embeddings, an OpenAI-compatible gateway, Langfuse observability, **LLM Guard** or **NeMo** guardrails (input + output), and **Qdrant** or **pgvector** for retrieval.

> Niyan is **not** a better Ollama chat UI. Ollama runs models; Niyan runs the **application environment** around them.

## Architecture

```
    Client → Gateway :4000 → Guardrails (input) → LiteLLM → Guardrails (output)
                               → Ollama (local chat + nomic-embed-text)
                               → OpenAI / Gemini / Anthropic (proprietary, optional)
                      → Langfuse (optional traces)
CLI / Admin UI → niyan-api :8100 → Docker Compose + niyan.yaml
                                 → Qdrant XOR pgvector (optional)
```

### Profiles

| Profile | Ollama |
|---------|--------|
| `mac` | **Host** Ollama (Metal) via `host.docker.internal` |
| `windows` | **Host** Ollama via `host.docker.internal` (Docker Desktop) |
| `linux-cpu` | Compose Ollama |
| `linux-gpu` | Compose Ollama + NVIDIA device reservation |

`profile: auto` picks `mac` / `windows` / `linux-cpu` / `linux-gpu` from the OS (and `nvidia-smi` on Linux).

## Quick start

### macOS / Linux

```bash
chmod +x install.sh scripts/smoke_test.sh scripts/rag_smoke_test.sh
./install.sh          # run as your normal user — do not use sudo
```

### Beta testers (no repo clone)

Pull-only Anaconda-style installer (private Niyan images + thin bash CLI): see **[docs/remote-install.md](docs/remote-install.md)**.

### Windows (PowerShell)

Prerequisites: [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Linux containers), [Ollama for Windows](https://ollama.com), Python 3.9+.

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
# open a new PowerShell (or: . $PROFILE), then:
niyan doctor
niyan up
```

Repo-local fallback: `.\niyan.cmd doctor`.

> **WSL2 alternative:** run the macOS/Linux `./install.sh` path inside Ubuntu on WSL2 with Docker Desktop WSL integration. That uses `linux-cpu` / `linux-gpu` (Compose Ollama), not the `windows` profile.

`install.sh` / `install.ps1` mirror Anaconda / `conda init`:

1. Creates `.venv` and `pip install -e ./cli` so the `niyan` entrypoint exists
2. Writes `niyan.yaml` / `.env` if missing
3. Runs **`niyan shell init`** — adds a marked block to `~/.zshrc`, `~/.bashrc`, or your **PowerShell profile** that sets `NIYAN_ROOT` and sources `shell/niyan.sh` or `shell/niyan.ps1`, so **`niyan` is on PATH in every new shell**

```bash
# >>> niyan initialize >>>  (bash/zsh)
export NIYAN_ROOT="/path/to/AI_Infrastructure"
export NIYAN_HOME="$NIYAN_ROOT"
. "$NIYAN_ROOT/shell/niyan.sh"
# <<< niyan initialize <<<
```

```powershell
# >>> niyan initialize >>>  (PowerShell)
$env:NIYAN_ROOT = 'C:\path\to\AI_Infrastructure'
$env:NIYAN_HOME = $env:NIYAN_ROOT
. 'C:\path\to\AI_Infrastructure\shell\niyan.ps1'
# <<< niyan initialize <<<
```

```bash
# refresh current shell once (Unix)
source ~/.zshrc   # or: source ~/.bashrc

niyan doctor
niyan up
niyan status
```

| Command | Purpose |
|---------|---------|
| `niyan shell init` | Wire `niyan` into your shell profile (also run by installers) |
| `niyan shell init --shell powershell` | Force PowerShell profile on Windows |
| `niyan shell init --reverse` | Remove the Niyan block from the shell rc / profile |
| `niyan init --shell` | Create `niyan.yaml` and run shell init |
| `./niyan.sh …` / `.\niyan.cmd …` | Repo-local fallback (no shell init required) |

Default admin: `admin` / `niyan`  
Default API key: `sk-niyan-local`

Optional: add **OpenAI / Gemini / Anthropic** keys in Admin → **Providers**, enable models under **Models → Proprietary**, then call the same gateway — [full guide](#proprietary-models-openai--gemini--anthropic).

**Test the proxy in the browser:** [http://127.0.0.1:4000/docs](http://127.0.0.1:4000/docs) (Authorize with `sk-niyan-local`). Details: [docs/testing.md](docs/testing.md).

## Installation troubleshooting

### Dev install vs remote (beta) install

| Path | When | What to run |
|------|------|-------------|
| **Dev** (this repo) | You have the source checkout and want the latest code | `./install.sh` then `niyan up --build` |
| **Remote / testers** | Pre-built images only; no local Docker build | `./install-remote.sh` or the curl installer — [docs/remote-install.md](docs/remote-install.md) |

Remote install materializes `~/.niyan` from published images. It does **not** pick up uncommitted changes in your checkout. For stack changes you are developing locally, use the dev path and `--build`.

### Do not run `sudo ./install.sh`

The installer creates `.venv` in the repo and runs `niyan shell init`, which edits `~/.zshrc` (or `~/.bashrc`). Running as root:

- Makes `.venv` and `niyan` **root-owned** (pip/CLI permission errors later)
- Can make `~/.zshrc` **root-owned** → `PermissionError` during shell init

**If you already used sudo:**

```bash
cd /path/to/AI_Infrastructure
sudo chown -R "$(whoami)" .venv ~/.zshrc 2>/dev/null
./install.sh   # without sudo
```

### Shell init failed (`Permission denied` on `~/.zshrc`)

Fix file ownership (above), then re-run `./install.sh` or `niyan shell init`.

Or skip shell wiring and use the repo-local CLI:

```bash
./niyan.sh doctor
./niyan.sh up --build
```

Remove a broken block: `niyan shell init --reverse`, then `niyan shell init` again.

### `niyan up` fails with Docker `content digest … not found`

Usually a **corrupted or incomplete image** in Docker’s local cache (often `ghcr.io/berriai/litellm:main-latest`), not a bug in the Niyan CLI. The Python `CalledProcessError` is just Compose exiting non-zero.

```bash
niyan down
docker pull ghcr.io/berriai/litellm:main-latest
docker pull langfuse/langfuse:2
niyan up --build
```

If it still fails:

```bash
docker builder prune -f
niyan up --build
```

## API usage (sample payloads)

All gateway calls use header `Authorization: Bearer sk-niyan-local`.  
Control-plane vector calls use an admin JWT (see login payload below).

### Chat completion

`POST http://127.0.0.1:4000/v1/chat/completions`

**Request payload:**

```json
{
  "model": "llama3.2:3b",
  "messages": [
    { "role": "user", "content": "Say hello in one short sentence." }
  ]
}
```

**curl:**

```bash
curl http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-niyan-local" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.2:3b",
    "messages": [
      { "role": "user", "content": "Say hello in one short sentence." }
    ]
  }'
```

Other chat models: `gemma2:2b` (pull first with `niyan model pull gemma2:2b`).

### Embeddings

1. Pull the embedding model via Niyan (same path as chat — Niyan maps to Ollama internally):

```bash
niyan embeddings pull
# or: niyan model pull nomic-embed-text
```

2. Embed text — `POST http://127.0.0.1:4000/v1/embeddings`

**Request payload (single string):**

```json
{
  "model": "nomic-embed-text",
  "input": "What is Niyan?"
}
```

**Request payload (batch):**

```json
{
  "model": "nomic-embed-text",
  "input": [
    "Niyan is an SLM stack manager",
    "Qdrant stores vectors for RAG"
  ]
}
```

**curl:**

```bash
curl http://127.0.0.1:4000/v1/embeddings \
  -H "Authorization: Bearer sk-niyan-local" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nomic-embed-text",
    "input": "What is Niyan?"
  }'
```

**Response shape (abridged):** `data[0].embedding` is a 768-float array for `nomic-embed-text`.

### Vector store (Qdrant or pgvector)

Off by default. Enable one provider and recreate:

```bash
niyan vector provider qdrant     # :6333
# or
niyan vector provider pgvector   # Postgres DB niyan_vectors
```

Admin UI: **Vectors** at [http://127.0.0.1:3080](http://127.0.0.1:3080).

#### Login (get admin token)

`POST http://127.0.0.1:8100/api/auth/login`

```json
{
  "username": "admin",
  "password": "niyan"
}
```

```bash
TOKEN=$(curl -sf http://127.0.0.1:8100/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"niyan"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
```

Use header `Authorization: Bearer $TOKEN` on the routes below.

#### Create collection

`POST http://127.0.0.1:8100/api/vector/collections`

```json
{
  "name": "docs",
  "size": 768
}
```

`size` must match the embedding model (`nomic-embed-text` → **768**).

#### Upsert points

`POST http://127.0.0.1:8100/api/vector/upsert`

```json
{
  "collection": "docs",
  "points": [
    {
      "id": "doc-1",
      "vector": [0.01, 0.02, 0.03],
      "payload": {
        "text": "Niyan local RAG stack",
        "source": "readme"
      }
    }
  ]
}
```

Replace `vector` with a real 768-dim embedding from `/v1/embeddings` (see end-to-end script below). `payload` is optional metadata returned on search.

#### Search

`POST http://127.0.0.1:8100/api/vector/search`

```json
{
  "collection": "docs",
  "vector": [0.01, 0.02, 0.03],
  "limit": 5
}
```

**Response shape (example):**

```json
{
  "hits": [
    {
      "id": "doc-1",
      "score": 0.99,
      "payload": { "text": "Niyan local RAG stack", "source": "readme" }
    }
  ]
}
```

#### End-to-end: embed → upsert → search

```bash
# 1) embed
VEC=$(curl -sf http://127.0.0.1:4000/v1/embeddings \
  -H "Authorization: Bearer sk-niyan-local" \
  -H "Content-Type: application/json" \
  -d '{"model":"nomic-embed-text","input":"Niyan local RAG"}' \
  | python3 -c 'import sys,json; print(json.dumps(json.load(sys.stdin)["data"][0]["embedding"]))')

# 2) create collection (idempotent enough to re-run after delete)
curl -sf http://127.0.0.1:8100/api/vector/collections \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"docs","size":768}'

# 3) upsert
curl -sf http://127.0.0.1:8100/api/vector/upsert \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{
    \"collection\": \"docs\",
    \"points\": [{
      \"id\": \"doc-1\",
      \"vector\": $VEC,
      \"payload\": {\"text\": \"Niyan local RAG\", \"source\": \"readme\"}
    }]
  }"

# 4) search
curl -sf http://127.0.0.1:8100/api/vector/search \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{
    \"collection\": \"docs\",
    \"vector\": $VEC,
    \"limit\": 5
  }"
```

Full walkthrough: [docs/quickstart.md](docs/quickstart.md).

**RAG smoke test** (embed → store → retrieve):

```bash
./scripts/rag_smoke_test.sh
```

General stack smoke: `./scripts/smoke_test.sh`.

## Repository layout

```
cli/           # Python Typer CLI (`niyan`)
api/           # FastAPI control plane
admin-ui/      # React + Vite admin console
services/      # gateway, litellm config, llm-guard, nemo
deploy/        # docker compose + profiles
configs/       # niyan.example.yaml
```

## CLI

```bash
niyan init | doctor | up | down | status | logs
niyan model list | pull | remove | enable | disable
niyan provider set openai|gemini|anthropic --api-key …
niyan provider status
niyan guardrails provider llm_guard|nemo
niyan vector provider qdrant|pgvector
niyan embeddings model nomic-embed-text [--pull]
niyan embeddings pull
niyan config show
```

Chat and embedding pulls for **local** models go through Niyan (API → Ollama). Proprietary models use the same gateway — see [Proprietary models (OpenAI / Gemini / Anthropic)](#proprietary-models-openai--gemini--anthropic) below.

## Proprietary models (OpenAI / Gemini / Anthropic)

Use **local Ollama models** for zero API cost, or **OpenAI / Gemini / Anthropic** when you want managed cloud quality — all are exposed through the same OpenAI-compatible gateway on `:4000`. You do **not** pull proprietary models; you **set a provider API key** and **enable** the model.

### Curated catalog

| Provider | Model id | Notes |
|----------|----------|--------|
| **ollama** (local) | `llama3.2:3b`, `gemma2:2b` | Pull into Ollama via `niyan model pull` |
| **openai** | `gpt-4o-mini`, `gpt-4o` | Requires OpenAI API key |
| **gemini** | `gemini-2.5-flash`, `gemini-3.5-flash` | Requires Google AI / Gemini API key |
| **anthropic** | `claude-haiku-4-5`, `claude-sonnet-5`, `claude-opus-5` | Requires Anthropic API key |

Embeddings stay on **local Ollama** (`nomic-embed-text`) for now. Proprietary chat models are configured in `niyan.yaml` under `providers` and `models`; LiteLLM routes are generated into `services/litellm/config.generated.yaml` on `niyan up` or when you save from the Admin UI.

### Setup (Admin UI — recommended)

1. Bring up the stack: `niyan up`
2. Open **Admin UI**: [http://127.0.0.1:3080](http://127.0.0.1:3080) (login: `admin` / `niyan`)
3. **Providers** — paste your cloud API key and enable the provider:
   - **OpenAI** — [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
   - **Google Gemini** — [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
   - **Anthropic** — [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys)
4. **Models** → **Proprietary (OpenAI / Gemini / Anthropic)** — toggle **Enable** for each model you want (e.g. `claude-sonnet-5`, `gemini-2.5-flash`, `gpt-4o-mini`)
   - If the key is missing, click **set key in Providers →** — it jumps to the right provider card
5. **Self-hosted (Ollama)** section is separate — use **Pull** there only for local models

Saving Providers or enabling a model regenerates LiteLLM config and restarts the `litellm` service automatically.

### Setup (CLI)

```bash
# 1) Store provider keys in niyan.yaml (never echoed back in full)
niyan provider set openai --api-key "$OPENAI_API_KEY"
niyan provider set gemini --api-key "$GEMINI_API_KEY"
niyan provider set anthropic --api-key "$ANTHROPIC_API_KEY"

# 2) Check configuration (shows last 4 chars only)
niyan provider status

# 3) Enable curated models (no pull — cloud models are API-routed)
niyan model enable gpt-4o-mini
niyan model enable gemini-2.5-flash
niyan model enable claude-sonnet-5

# 4) Refresh stack so LiteLLM picks up routes + env keys
niyan up

# 5) Confirm models are registered
curl -s http://127.0.0.1:4000/v1/models \
  -H "Authorization: Bearer sk-niyan-local" \
  | python3 -m json.tool
```

Disable a cloud model: `niyan model disable gpt-4o-mini`

### Usage (same gateway as local models)

All requests use the **Niyan gateway API key** (`Authorization: Bearer sk-niyan-local` by default). Niyan forwards to LiteLLM, which calls OpenAI, Gemini, or Anthropic using **your** provider key stored in `niyan.yaml`.

**Gemini 2.5 Flash:**

```bash
curl http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-niyan-local" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.5-flash",
    "messages": [{"role": "user", "content": "Say hello in one short sentence."}]
  }'
```

**OpenAI GPT-4o mini:**

```bash
curl http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-niyan-local" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Say hello in one short sentence."}]
  }'
```

**Anthropic Claude Sonnet 5:**

```bash
curl http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-niyan-local" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-5",
    "messages": [{"role": "user", "content": "Say hello in one short sentence."}]
  }'
```

**Swagger UI:** [http://127.0.0.1:4000/docs](http://127.0.0.1:4000/docs) — Authorize with `sk-niyan-local`, pick the model id, send a chat completion.

Responses include a `niyan` block with token usage and estimated API cost when using proprietary models.

### Enterprise AI Policy (domain routing)

Instead of picking a concrete model, apps can send a **domain id** as `model` (e.g. `finance`, `marketing`, `sales`, `research`, `summary`, `support`, `legal`). In **Admin → Enterprise AI Policy**, flip the **Self-hosted | Proprietary** bar per domain. Proprietary defaults to Gemini (`gemini-2.5-flash`).

```bash
curl http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-niyan-local" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "finance",
    "messages": [{"role": "user", "content": "Summarize Q3 cash flow risks."}]
  }'
```

The gateway remaps the domain to the configured local or proprietary model. The response `niyan` block includes `domain`, `resolved_model`, and `policy_deployment`. Real model ids (e.g. `llama3.2:3b`, `gemini-2.5-flash`) still work unchanged. Auto routing by query complexity is planned later.

### Load Testing (Locust)

**Admin → Load Testing** runs Locust against:

- Gateway chat (`/v1/chat/completions`)
- Gateway embeddings (`/v1/embeddings`)
- Gateway domain ids (Enterprise AI Policy)
- One custom HTTP endpoint (with SSRF guards; enable “Allow internal URLs” for private hosts)

Configure concurrent users (max 50), spawn rate, and duration (max 600s). Only **one** run at a time. Proprietary targets show a cost warning. Watch live RPS / p50–p99 / failures in the UI, then download **JSON**, **HTML**, or **CSV** reports from history.

Requires the `loadtest` container (`niyan up --build`). Artifacts land under `data/loadtests/{run_id}/`.

### Configuration (`niyan.yaml`)

Provider keys and model enablement live in `niyan.yaml` (created by `install.sh` / `niyan init`):

```yaml
providers:
  openai:
    enabled: true
    api_key: "sk-..."          # set via Admin → Providers or `niyan provider set`
  gemini:
    enabled: true
    api_key: "AIza..."
  anthropic:
    enabled: true
    api_key: "sk-ant-..."

models:
  - id: llama3.2:3b
    provider: ollama
    enabled: true
  - id: gemini-2.5-flash
    provider: gemini
    enabled: true              # only routed when provider key is set + enabled
  - id: claude-sonnet-5
    provider: anthropic
    enabled: true

pricing:                       # used for dashboard cost estimates (USD per 1M tokens)
  openai:
    gpt-4o-mini: { input_per_1m: 0.15, output_per_1m: 0.60 }
  gemini:
    gemini-2.5-flash: { input_per_1m: 0.30, output_per_1m: 2.50 }
    gemini-3.5-flash: { input_per_1m: 1.50, output_per_1m: 9.00 }
  anthropic:
    claude-haiku-4-5: { input_per_1m: 1.00, output_per_1m: 5.00 }
    claude-sonnet-5: { input_per_1m: 3.00, output_per_1m: 15.00 }
    claude-opus-5: { input_per_1m: 15.00, output_per_1m: 75.00 }
```

After editing `niyan.yaml` by hand, run `niyan up` to regenerate LiteLLM config and reload env vars.

### Usage & cost dashboard

Open **Dashboard** in the Admin UI ([http://127.0.0.1:3080](http://127.0.0.1:3080)):

- **Time range** presets (24h / 7d / 30d / 90d) or custom dates — same idea as Langfuse
- **Application filter** — **All** or a specific project (`Enterprise-Functions`, `finance`, …) so you can see which app used how much of the shared Niyan gateway
- **Tokens** and **proprietary API cost (USD)** pulled from **Langfuse Daily Metrics** (Langfuse prices OpenAI/Gemini/Anthropic from its model catalog)
- **Local vs proprietary** comparison — self-hosted Ollama cost is **N/A for now** (open-source cost later); OpenAI/Gemini/Anthropic show Langfuse cost
- Daily cost bars for the selected window
- Requires `observability.public_key` / `secret_key` in `niyan.yaml` (Langfuse project keys)

Attribute traffic per project by sending a header (demo apps already do this):

```bash
curl http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-niyan-local" \
  -H "X-Niyan-Application: Enterprise-Functions" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:3b","messages":[{"role":"user","content":"Hello"}]}'
```

Unlabelled requests show up as `Unattributed`. The **Applications** tab lists every project that has hit the gateway, with token share for the top five.

Langfuse UI ([http://127.0.0.1:3100](http://127.0.0.1:3100)) remains the place for full per-trace drill-down. If proprietary cost stays at zero despite traffic, check **Langfuse → Models** that the model id matches (e.g. `gemini-2.5-flash`, `claude-sonnet-5`).

### Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Invalid model name … gemini-2.5-flash` | Model not enabled or LiteLLM not refreshed — `niyan model enable gemini-2.5-flash` then `niyan up` |
| Pull on Gemini/OpenAI/Anthropic fails (Ollama 500) | Cloud models must be **enabled**, not pulled — use Models → Proprietary or `niyan model enable` |
| `Provider … not configured` | Set key under **Providers** or `niyan provider set anthropic --api-key …` |
| Model missing from `/v1/models` | Provider disabled, key empty, or model `enabled: false` in `niyan.yaml` |
| Cost stays $0 for Gemini/OpenAI/Anthropic on Dashboard | Ensure Langfuse keys in `niyan.yaml`; open Dashboard range; confirm cost on the trace in Langfuse; model id must match Langfuse Models catalog |
| Dashboard shows Langfuse unavailable | Set `observability.public_key` / `secret_key`; confirm Langfuse reachable at `:3100` |

Intelligent routing between local and proprietary models (auto-pick cheapest/fastest) is planned for a later release.

## Configuration

Edit `niyan.yaml` (created by `niyan init`). Single source of truth for models, proxy keys, observability, guardrails, embeddings, and vector provider. For **OpenAI / Gemini / Anthropic** keys, model enablement, and pricing defaults, see [Proprietary models (OpenAI / Gemini / Anthropic)](#proprietary-models-openai--gemini--anthropic) above.

## Prototype scope

**In:** Ollama, LiteLLM, gateway, Langfuse, LLM Guard + NeMo (input and output scanners), Qdrant + pgvector (selectable), `nomic-embed-text`, OpenAI + Gemini + Anthropic (keys via portal), token/cost dashboard with per-application filter, control plane, admin UI, CLI.

**Later:** intelligent routing local↔cloud, vLLM, Triton/TensorRT-LLM, Keycloak, Prometheus/Grafana, Helm, Go CLI binary, encrypted key vault.
