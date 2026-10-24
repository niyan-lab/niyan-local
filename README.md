# Niyan (local)

**Anaconda-style SLM stack manager** for your machine: one install brings up an OpenAI-compatible gateway, control plane, Admin UI, optional cloud providers, guardrails, and vectors.

This repo is **local / Docker Compose only**. Kubernetes lives in [`niyan-complete`](https://github.com/niyan-lab/niyan-complete). See [docs/CHARTER.md](docs/CHARTER.md).

```
Clients  →  gateway :4000  →  LiteLLM (internal)  →  Ollama / OpenAI / Gemini / Anthropic
Browser  →  admin-ui :3080  →  niyan-api :8100  →  Postgres (runtime config)
```

LiteLLM is never exposed to clients. Postgres is the live config store; Redis is a gateway cache; `niyan.yaml` is first-boot seed.

## Prerequisites

- Docker Desktop (or Engine + Compose v2)
- Python 3.9+ (on Linux, also install the `python3-venv` package)
- **macOS / Windows:** [Ollama](https://ollama.com) on the **host**
- **Linux:** Ollama runs in Compose (`linux-cpu` / `linux-gpu`)

Do **not** run the installer with `sudo`.

## Install

### macOS / Linux

```bash
git clone https://github.com/niyan-lab/niyan-local.git
cd niyan-local
chmod +x install.sh uninstall.sh
./install.sh
source ~/.zshrc    # or: source ~/.bashrc
```

### Windows (PowerShell)

Docker Desktop (Linux containers) + Ollama for Windows + Python 3.9+.

```powershell
git clone https://github.com/niyan-lab/niyan-local.git
cd niyan-local
powershell -ExecutionPolicy Bypass -File .\install.ps1
# new PowerShell, or: . $PROFILE
```

`install.sh` / `install.ps1` create `.venv`, install the `niyan` CLI, seed `niyan.yaml` / `.env` (chmod 600) with **per-install random secrets**, and add a marked block to your shell profile so `niyan` is on PATH.

## Secrets

There are no shared default credentials. On first run `install.sh` / `install.ps1` (via `niyan secrets init`) generate:

- `niyan.yaml`: `admin_auth.password`, `admin_auth.jwt_secret`, `proxy.api_keys` (gateway / LiteLLM master key). This is the single source for these three, for both the from-source and the pull-only installer (which mirrors them into `~/.niyan/stack/.env` for Compose).
- `.env`: `POSTGRES_PASSWORD`, `LANGFUSE_NEXTAUTH_SECRET`, `LANGFUSE_SALT`, `LANGFUSE_ENCRYPTION_KEY`.

Re-running the installer keeps existing strong values. The admin password is printed at the end of an install that generated it (it then sits in your terminal scrollback — clear it on shared screens); later use `niyan secrets show` (`--all` adds the API key and JWT secret, `--field password` prints one raw value for scripts). `niyan up`, the gateway and the control API refuse to start with empty or old default secrets. For throwaway dev/tests only, `NIYAN_ALLOW_INSECURE_DEFAULTS=1` (exactly `1`) bypasses that check with a loud warning; it is not wired into the release/pull-only Compose files. LiteLLM and Langfuse do not check their own secrets — the `niyan up` pre-check (and `~/.niyan/bin/niyan up` for pull-only installs) is what guards them. Secrets are never stored in Postgres/Redis; `/api/config` returns them masked.

**Gateway keys are read-only in the Admin UI** (the save endpoints return 409 for a changed key), so the Gateway page always shows the key the gateway enforces. To rotate: `niyan secrets rotate gateway-key` (pull-only: `~/.niyan/bin/niyan secrets rotate gateway-key`), then `niyan up`. Read the new key with `niyan gateway keys --plain`.

### Upgrading from an older install (shared default secrets)

Builds before per-install secrets shipped `niyan` / `sk-niyan-local` / `change-me…` defaults. Just pull and re-run the installer — **with Docker running**:

```bash
git pull && ./install.sh        # pull-only: re-run the bootstrap installer
niyan up
niyan secrets show              # new admin password
```

What happens, without wiping data:

- **Postgres** (`niyan_niyan_pg` volume exists): a new password is applied in place with `ALTER USER` (over the container's local socket), verified over TCP, then written to `.env`. `niyan up` recreates containers with it.
- **Langfuse** `LANGFUSE_NEXTAUTH_SECRET` is rotated (only logs users out). `LANGFUSE_SALT` / `LANGFUSE_ENCRYPTION_KEY` are rotated only if no Langfuse rows depend on them (API keys / stored LLM keys). Otherwise (a **confirmed** non-zero count) the old public value is **kept**, marked `NIYAN_LEGACY_LANGFUSE_SALT=1` / `NIYAN_LEGACY_LANGFUSE_ENCRYPTION_KEY=1` in `.env`, and the installer warns: anyone with repo access knows that key. Marked keys are re-counted on every install and rotated as soon as nothing depends on them. If the count itself fails (Postgres restarting, exec error/timeout) it is retried 3× with backoff; if it still fails the installer stops **before changing anything** (no marker, no rotation) and `niyan up` keeps refusing until you re-run the installer. A missing `langfuse` database counts as 0 rows. The Langfuse counts run before the Postgres password is rotated.
- **Admin password, JWT secret, gateway key** in `niyan.yaml` are regenerated. Old secrets stored in the Postgres config table are scrubbed on API start and an admin-UI save cannot write a default back. Update clients that used `sk-niyan-local` to `niyan gateway keys --plain`.
- **Docker not running**: the installer refuses (exit 2) and changes nothing, because it cannot tell whether data exists.

```bash
export NIYAN_API_KEY="$(niyan gateway keys --plain | head -1)"
```

## Start

```bash
niyan doctor
niyan up
niyan status
```

Repo-local fallback (no shell init): `./niyan.sh …` or `.\niyan.cmd …`

| | |
|---|---|
| Admin UI | http://127.0.0.1:3080 (`admin` / password from `niyan secrets show`) |
| Gateway (OpenAI API) | http://127.0.0.1:4000 — Swagger at `/docs` |
| Control API | http://127.0.0.1:8100 |
| Gateway API key | generated per install — `niyan gateway keys --plain` (export as `NIYAN_API_KEY`) |

Pull local models (Mac/Windows: host Ollama; Linux: Compose):

```bash
niyan model pull llama3.2:3b
niyan embeddings pull
```

Optional cloud models: Admin → **Providers** (paste key) → **Models → Proprietary** (enable). Same gateway. Details: [docs/quickstart.md](docs/quickstart.md).

## Uninstall

Stops Compose, removes the `# >>> niyan initialize >>>` block from your shell profile, and deletes `.venv`. **Leaves this git checkout in place.**

```bash
./uninstall.sh                 # keep Docker volumes
./uninstall.sh --volumes       # also delete Postgres/Redis volumes
./uninstall.sh --keep-config   # keep niyan.yaml and .env
./uninstall.sh --yes           # no prompt
```

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1 -Volumes -Yes
```

Equivalent CLI (after install): `niyan uninstall` / `niyan uninstall --volumes -y`.

Stop without uninstalling: `niyan down`.

## Pull-only testers (no source build)

Pre-built GHCR images + thin CLI under `~/.niyan`. See [docs/remote-install.md](docs/remote-install.md).

```bash
./bootstrap/install.sh     # from this checkout, for operator smoke
niyan uninstall            # removes ~/.niyan (remote CLI)
```

## Layout

```
install.sh / install.ps1     from-source installer
uninstall.sh / uninstall.ps1 from-source uninstall
cli/                         Python `niyan` CLI
api/                         FastAPI control plane (:8100)
admin-ui/                    Admin console (:3080)
services/                    gateway, LiteLLM config, guardrails
deploy/                      Docker Compose
configs/                     niyan.example.yaml seed
bootstrap/                   pull-only bundle (GHCR)
```

## Docs

| Doc | |
|-----|--|
| [docs/quickstart.md](docs/quickstart.md) | Chat, embeddings, vectors, proprietary models |
| [docs/testing.md](docs/testing.md) | Gateway Swagger |
| [docs/Arch.md](docs/Arch.md) | Routing and runtime config |
| [docs/remote-install.md](docs/remote-install.md) | GHCR / beta pull-only path |
| [docs/CHARTER.md](docs/CHARTER.md) | Local-only scope |

## License

Copyright 2026 Niyan Lab.

Licensed under the [Apache License, Version 2.0](LICENSE). Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
