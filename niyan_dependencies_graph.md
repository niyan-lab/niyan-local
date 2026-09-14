# Niyan Ecosystem Dependencies & Architecture

This document provides a comprehensive dependency graph and service-by-service breakdown of the Niyan AI Infrastructure platform. It maps out how the microservices in the `deploy/docker-compose.yml` and `/services` directories interact, including ports, purposes, and communication flows.

---

## Architectural Dependency Graph

This diagram shows the complete dependency flow. Solid lines (`-->`) represent direct runtime HTTP/gRPC/TCP dependency calls, while dashed lines (`-.->`) represent administration, configuration, or testing actions.

```mermaid
graph TD
    subgraph Clients["1. Frontend & Client Entrypoints"]
        UI["Admin Console (admin-ui)"]
        ClientApp["End-User / Client Application"]
    end

    subgraph Management["2. Core Control Plane"]
        API["Control Plane API (niyan-api)"]
        DockerD["Docker Host Daemon (/var/run/docker.sock)"]
    end

    subgraph GatewayProxy["3. Routing & Security Layer"]
        GW["API Gateway (gateway)"]
        LiteLLM["LiteLLM Routing Proxy (litellm)"]
    end

    subgraph Guardrails["4. Guardrails & Content Safety"]
        LLMGuard["LLM Guard (guardrails)"]
        NemoGuard["NeMo Guardrails (nemo-guardrails)"]
    end

    subgraph DataObservability["5. Data, Caching & Observability"]
        Redis["Redis Cache & Rate Limiting"]
        LF["Langfuse Web (langfuse-web)"]
        Postgres["PostgreSQL Vector DB (postgres)"]
        Qdrant["Qdrant Vector DB (qdrant)"]
    end

    subgraph LLMProviders["6. LLM Backends & Providers"]
        Ollama["Ollama (local models)"]
        ExtAPI["External LLM APIs (OpenAI, Gemini, etc.)"]
    end

    subgraph LoadTesting["7. Performance Validation"]
        Locust["Locust Runner (loadtest)"]
    end

    %% User Interactions
    UI -->|Admin actions / Queries| API
    ClientApp -->|Chat/Embeddings completions| GW

    %% Control Plane Dependencies
    API -.->|Inspect / Restart containers| DockerD
    API -.->|Rebuild config.generated.yaml| LiteLLM
    API -->|Read metrics / Logs| LF
    API -->|Vector stores| Postgres
    API -->|Vector stores| Qdrant
    API -.->|Trigger load testing| Locust
    API -->|Verify settings| GW
    API -->|Verify cache| Redis

    %% Gateway Runtime Flow
    GW -->|1. Content & Prompt scanning| LLMGuard
    GW -->|1. Content & Prompt scanning| NemoGuard
    GW -->|2. Route / Load-balance| LiteLLM
    GW -->|Rate limiting / Cache| Redis
    GW -->|Trace events / Observability| LF

    %% LiteLLM Runtime Flow
    LiteLLM -->|Rate limiting / Metadata| Redis
    LiteLLM -->|Trace events / Observability| LF
    LiteLLM -->|Model dispatch| Ollama
    LiteLLM -->|Model dispatch| ExtAPI

    %% Observability DB
    LF -->|Read/Write analytics| Postgres

    %% Load Testing Loop
    Locust -->|Inject high traffic| GW
```

---

## Detailed Service Catalog & Matrix

| Service Name | Source Path | Ports (Internal / External) | Key Purpose / Functionality | Direct Dependencies |
| :--- | :--- | :--- | :--- | :--- |
| **admin-ui** | `/admin-ui` | `80` / `3080` | Single Page Application (Vite + React/Vue) providing the Admin dashboard for managing keys, configs, and viewing metrics. | `niyan-api` |
| **niyan-api** | `/api` | `8100` / `8100` | The orchestration control plane. It interacts with the Docker daemon to monitor health, manages model configurations, connects to vector stores, and triggers load tests. | `gateway`, `redis`, `loadtest`, `postgres`, `qdrant`, `langfuse-web`, Docker Daemon |
| **gateway** | `/services/gateway` | `4000` / `4000` | Entrypoint for client LLM traffic. Manages API keys, applies enterprise safety policies, routes requests to guardrails, and proxies traffic to LiteLLM. | `litellm`, `redis`, `guardrails`, `nemo-guardrails`, `langfuse-web` |
| **litellm** | `/services/litellm` (Config) | `4001` / None | Standardized OpenAI-compatible routing and load balancing proxy. Translates requests to Ollama or external LLM providers. | `redis`, `langfuse-web`, `ollama` |
| **guardrails** | `/services/llm-guard` | `8088` / None | Python service running `llm-guard` to scan prompts/responses for injection, PII leak, toxicity, and general safety. | None |
| **nemo-guardrails** | `/services/nemo` | `8089` / None | NeMo Guardrails engine for conversational guardrails and dialog guidance. | None |
| **loadtest** | `/services/loadtest` | `5000` / None | locust-based loader. Spawns headless worker tasks on-demand via the Control Plane to execute throughput & latency stress tests against the gateway. | `gateway` |
| **langfuse-web** | `/services/langfuse` (Config) | `3000` / `3100` | Analytics and LLM engineering dashboard. Tracks trace history, prompt management, and metrics. | `postgres` |
| **postgres** | Docker Hub | `5432` / None | Relational DB used by Langfuse to store traces and pgvector for native PostgreSQL vector storage. | None |
| **redis** | Docker Hub | `6379` / None | High-performance memory cache for API Gateway and LiteLLM rate-limiting and metadata caching. | None |
| **qdrant** | Docker Hub | `6333` / `6333` | Vector database for storing and querying text embeddings. | None |
| **ollama** | Docker Hub | `11434` / `11434` | Locally deployed LLM provider running models such as llama3, mistral, or nomic-embed-text. | None |

---

## Direct vs. Runtime Call Lifecycle

### 1. Control Plane & Configuration Flow
1. **Admin** saves a configuration change (e.g., adding an API Key or LLM Provider) in **admin-ui**.
2. **niyan-api** processes the change, writes/regenerates `/services/litellm/config.generated.yaml`.
3. **niyan-api** commands **Docker Daemon** via `/var/run/docker.sock` to restart/reload the `litellm` container to apply the changes.

### 2. LLM Completion Flow (Runtime)
1. **ClientApp** makes a request to `http://127.0.0.1:4000/v1/chat/completions`.
2. **gateway** checks API keys against **Redis** cache.
3. **gateway** invokes **guardrails** / **nemo-guardrails** to scan the incoming prompt.
4. If valid, **gateway** forwards the request to **litellm**.
5. **litellm** resolves the routing, fetches appropriate API credentials, and invokes either **ollama** (local) or **External APIs** (Gemini/OpenAI).
6. **litellm** and **gateway** report trace telemetry back to **langfuse-web** asynchronously.
7. The response is returned to the client.
