# Niyan architecture

## Control plane

- **CLI (`niyan`)** — Typer app; bootstraps Compose before API is up; then uses niyan-api for status/models.
- **niyan-api** — FastAPI on `:8100`; JWT admin auth; config CRUD; Docker health; Ollama pull; vector collections.
- **Admin UI** — React/Vite on `:3080`; talks only to niyan-api.

## Data plane

```
Client
  → gateway:4000 (OpenAI API, auth, guardrails in/out, Langfuse metadata)
    → litellm:4001 (model routing)
      → ollama / openai / gemini (host Ollama on Mac/Windows; Compose Ollama on Linux; cloud keys via Providers)
         chat: llama / gemma
         embeddings: nomic-embed-text
```

Guardrails: exactly one of

- `guardrails` service (LLM Guard profile `guard-llm`) on `:8088`
- `nemo-guardrails` service (profile `guard-nemo`) on `:8089`

Observability: Langfuse web + Postgres (`obs` profile).

## Vectors & embeddings

```
Client → gateway /v1/embeddings → LiteLLM → Ollama (nomic-embed-text)
Admin / CLI → niyan-api /api/vector/* → Qdrant XOR pgvector
```

Vector store: exactly one of (when `vector.enabled: true`)

- **Qdrant** — Compose profile `vector-qdrant` on `:6333`
- **pgvector** — Compose profile `vector-pg` (shared Postgres with Langfuse; DB `niyan_vectors`)

Embeddings stay on Ollama (no separate embedding microservice). Default model: `nomic-embed-text` (768-dim).

## Config

**Postgres** (`niyan_runtime_config`) is the live store. **Redis** (`niyan:config:*`) is a gateway cache for policy and Langfuse keys. **`niyan.yaml`** is first-boot seed and fallback if Postgres is down. Compose profiles and env vars are still derived by the CLI `local_compose.build_env` / `compose_cmd` from the seed file at `niyan up` time.

See [Arch.md](Arch.md) for the full config and routing design.
