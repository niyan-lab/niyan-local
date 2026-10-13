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
- Python 3.9+
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

`install.sh` / `install.ps1` create `.venv`, install the `niyan` CLI, seed `niyan.yaml` / `.env`, and add a marked block to your shell profile so `niyan` is on PATH.

## Start

```bash
niyan doctor
niyan up
niyan status
```

Repo-local fallback (no shell init): `./niyan.sh …` or `.\niyan.cmd …`

| | |
|---|---|
| Admin UI | http://127.0.0.1:3080 (`admin` / `niyan`) |
| Gateway (OpenAI API) | http://127.0.0.1:4000 — Swagger at `/docs` |
| Control API | http://127.0.0.1:8100 |
| Default API key | `sk-niyan-local` |

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
