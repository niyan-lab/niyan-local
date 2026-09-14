# Niyan Quickstart

## What Niyan is

Niyan is an **Anaconda-style environment manager for open SLMs**. It is not a replacement for Ollama’s chat UX.

It wires together:

- **Ollama** (Llama / Gemma + embedding models)
- **OpenAI / Gemini / Anthropic** (optional proprietary chat via the same gateway)
- **LiteLLM** (internal OpenAI router → Ollama and/or cloud providers)
- **Niyan Gateway** (`:4000`) — OpenAI-compatible API + guardrails + Langfuse metadata
- **Langfuse** (optional observability)
- **LLM Guard *or* NeMo** (one active provider)
- **Qdrant *or* pgvector** (optional vector store)
- **niyan-api** control plane + **Admin UI**

## Prerequisites

- Docker + Docker Compose v2 (Docker Desktop on macOS / Windows)
- Python 3.9+
- **macOS / Windows:** [Ollama](https://ollama.com) installed and running on the **host** (Metal on Mac; Docker Desktop uses `host.docker.internal`)
- **Linux:** Ollama runs in Compose (`ollama` profile), unless you override `ollama.host`
- **Windows alternative:** WSL2 Ubuntu + Docker Desktop WSL integration, then use `./install.sh` (Linux profiles)

## Install

### macOS / Linux

```bash
cd /path/to/AI_Infrastructure
chmod +x install.sh scripts/smoke_test.sh scripts/rag_smoke_test.sh
./install.sh
```

### Windows

```powershell
cd C:\path\to\AI_Infrastructure
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

This does three things (same idea as Anaconda/`conda init`):

1. Creates `.venv` and `pip install -e ./cli` so the `niyan` entrypoint exists
2. Writes `niyan.yaml` / `.env` if missing
3. Runs **`niyan shell init`** — adds a marked block to `~/.zshrc`, `~/.bashrc`, or your **PowerShell profile** that sets `NIYAN_ROOT` and sources `shell/niyan.sh` / `shell/niyan.ps1` so **`niyan` is on PATH in every new shell**

```bash
# refresh current shell once (Unix)
source ~/.zshrc   # or: source ~/.bashrc

# PowerShell
. $PROFILE
```

Remove the shell hook: `niyan shell init --reverse`.

## Bring up

```bash
niyan doctor
niyan up
niyan status
```

Pull chat and embedding models via Niyan (internally Ollama — host on Mac/Windows, Compose on Linux):

```bash
niyan model pull              # all enabled chat models + embedding model
niyan model pull llama3.2:3b
niyan model pull gemma2:2b
niyan embeddings pull         # configured embeddings.model (default nomic-embed-text)
```

## Proprietary models (OpenAI / Gemini / Anthropic)

Use **local Ollama models** for zero API cost, or **OpenAI / Gemini / Anthropic** for managed cloud quality — all go through the same OpenAI-compatible gateway on `:4000`. You do **not** pull proprietary models; you **set a provider API key** and **enable** the model.

Full reference (YAML, troubleshooting, dashboard): [README — Proprietary models](../README.md#proprietary-models-openai--gemini--anthropic).

### Curated catalog

| Provider | Model id | Notes |
|----------|----------|--------|
| **ollama** (local) | `llama3.2:3b`, `gemma2:2b` | Pull via `niyan model pull` |
| **openai** | `gpt-4o-mini`, `gpt-4o` | Requires OpenAI API key |
| **gemini** | `gemini-2.5-flash`, `gemini-3.5-flash` | Requires Google AI / Gemini API key |
| **anthropic** | `claude-haiku-4-5`, `claude-sonnet-5`, `claude-opus-5` | Requires Anthropic API key |

Embeddings stay on **local Ollama** (`nomic-embed-text`). LiteLLM routes are written to `services/litellm/config.generated.yaml` on `niyan up` or when you save from the Admin UI.

### Setup (Admin UI — recommended)

1. `niyan up`
2. Open **Admin UI**: [http://127.0.0.1:3080](http://127.0.0.1:3080) (`admin` / `niyan`)
3. **Providers** — paste your cloud API key and enable the provider:
   - **OpenAI** — [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
   - **Google Gemini** — [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
   - **Anthropic** — [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys)
4. **Models** → **Proprietary (OpenAI / Gemini / Anthropic)** — toggle **Enable** for each model (`claude-sonnet-5`, `gemini-2.5-flash`, `gpt-4o-mini`, …)
   - Missing key? Click **set key in Providers →** to jump to the right card
5. **Self-hosted (Ollama)** is separate — use **Pull** only for local models

Saving Providers or enabling a model regenerates LiteLLM config and restarts `litellm` automatically.

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
niyan model enable gemini-3.5-flash
niyan model enable claude-sonnet-5

# 4) Refresh stack so LiteLLM picks up routes + env keys
niyan up

# 5) Confirm models are registered
curl -s http://127.0.0.1:4000/v1/models \
  -H "Authorization: Bearer sk-niyan-local" \
  | python3 -m json.tool
```

Disable: `niyan model disable gpt-4o-mini`

### Usage (same gateway as local models)

Requests use the **Niyan gateway API key** (`Authorization: Bearer sk-niyan-local` by default). LiteLLM calls OpenAI/Gemini with **your** provider key from `niyan.yaml`.

**Gemini:**

```bash
curl http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-niyan-local" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.5-flash",
    "messages": [{"role": "user", "content": "Hello from Niyan"}]
  }'
```

**OpenAI:**

```bash
curl http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-niyan-local" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello from Niyan"}]
  }'
```

Swagger: [http://127.0.0.1:4000/docs](http://127.0.0.1:4000/docs) — Authorize with `sk-niyan-local`.

Responses may include a `niyan` block with tokens and estimated API cost for proprietary calls.

### Enterprise AI Policy (domain routing)

Send a domain id as `model` (`finance`, `marketing`, `sales`, `research`, `summary`, …). Configure Self-hosted vs Proprietary (default Gemini `gemini-2.5-flash`) under **Admin → Enterprise AI Policy**.

```bash
curl http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-niyan-local" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "summary",
    "messages": [{"role": "user", "content": "Summarize this in three bullets."}]
  }'
```

### Load Testing

Open **Admin → Load Testing** to run Locust against gateway chat/embeddings/domains or a custom URL. Caps: 50 concurrent users, 600s duration, one active run. Download JSON/HTML/CSV reports when finished. Rebuild once so the `loadtest` service is available: `niyan up --build`.

### Configuration (`niyan.yaml`)

```yaml
providers:
  openai:
    enabled: true
    api_key: "sk-..."          # Admin → Providers or `niyan provider set`
  gemini:
    enabled: true
    api_key: "AIza..."

models:
  - id: llama3.2:3b
    provider: ollama
    enabled: true
  - id: gemini-2.5-flash
    provider: gemini
    enabled: true              # routed only when provider key is set + enabled

pricing:                       # dashboard cost estimates (USD per 1M tokens)
  openai:
    gpt-4o-mini: { input_per_1m: 0.15, output_per_1m: 0.60 }
  gemini:
    gemini-2.5-flash: { input_per_1m: 0.30, output_per_1m: 2.50 }
    gemini-3.5-flash: { input_per_1m: 1.50, output_per_1m: 9.00 }
```

After hand-editing `niyan.yaml`, run `niyan up`.

### Usage & cost dashboard

**Dashboard** in Admin UI ([http://127.0.0.1:3080](http://127.0.0.1:3080)):

- Time range presets (24h / 7d / 30d / 90d) or custom dates
- **Tokens** and **proprietary API cost** from **Langfuse** (model catalog pricing)
- **Local vs proprietary** — Ollama cost N/A for now; OpenAI/Gemini show Langfuse cost
- Requires observability keys in `niyan.yaml`

### Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Invalid model name … gemini-2.5-flash` | `niyan model enable gemini-2.5-flash` then `niyan up` |
| Pull on Gemini/OpenAI fails (Ollama 500) | Cloud models are **enabled**, not pulled |
| `Provider … not configured` | **Providers** tab or `niyan provider set … --api-key …` |
| Model missing from `/v1/models` | Provider disabled, empty key, or model `enabled: false` |
| Dashboard cost empty / Langfuse unavailable | Set `observability.public_key` / `secret_key`; confirm cost on the Langfuse trace |

Intelligent local↔cloud routing is planned later.

## OpenAI-compatible call (local)

```bash
curl http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-niyan-local" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:3b","messages":[{"role":"user","content":"Hello"}]}'
```

## Embeddings

```bash
curl http://127.0.0.1:4000/v1/embeddings \
  -H "Authorization: Bearer sk-niyan-local" \
  -H "Content-Type: application/json" \
  -d '{"model":"nomic-embed-text","input":"What is Niyan?"}'
```

## Vector store (optional)

Disabled by default so `niyan up` stays light. Enable Qdrant (or pgvector) and recreate:

```bash
niyan vector provider qdrant
# or: niyan vector provider pgvector
```

Then create a collection, upsert, and search via the control plane (admin JWT):

```bash
# login
TOKEN=$(curl -sf http://127.0.0.1:8100/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"niyan"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

curl -sf http://127.0.0.1:8100/api/vector/collections \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"docs","size":768}'
```

Use gateway embeddings to produce vectors, then `POST /api/vector/upsert` and `POST /api/vector/search`.

## URLs

| Surface | URL |
|---------|-----|
| OpenAI chat | http://127.0.0.1:4000/v1/chat/completions |
| OpenAI embeddings | http://127.0.0.1:4000/v1/embeddings |
| **Proxy Swagger (try requests)** | **http://127.0.0.1:4000/docs** |
| Control plane docs | http://127.0.0.1:8100/docs |
| Admin console | http://127.0.0.1:3080 (admin / niyan) |
| Admin → Providers / Models | http://127.0.0.1:3080 (OpenAI / Gemini / Anthropic keys + enable) |
| Langfuse (bundled) | http://127.0.0.1:3100 |
| Qdrant (when enabled) | http://127.0.0.1:6333 |

See [testing.md](testing.md) for Authorize + Try-it-out steps.

> If you already run Langfuse on `:3000`, Niyan maps its bundled instance to **`:3100`** by default (`LANGFUSE_PORT`). To reuse your existing Langfuse instead, set `observability.enabled: false` (or leave keys pointed at `http://host.docker.internal:3000` and skip the `obs` profile).

## Switch guardrails provider

```bash
niyan guardrails provider nemo
# or
niyan guardrails provider llm_guard
```

Only one provider Compose profile runs at a time.

## Tear down

```bash
niyan down
```
