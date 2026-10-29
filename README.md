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
niyan doctor && niyan up --build
```

Already have niyan-complete installed? See [Two checkouts on one machine](#two-checkouts-on-one-machine): the last `./install.sh` decides which repo `niyan` controls.

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

There are no shared default credentials. `./install.sh` (via `niyan secrets init`) generates per-install secrets in `niyan.yaml` (admin password, JWT secret, gateway key) and `.env` (Postgres, Langfuse); both are chmod 600 and never stored in Postgres/Redis.

- **Show:** `niyan secrets show` (`--all` adds the API key and JWT secret, `--field password` prints one raw value for scripts).
- **Refuses defaults:** `niyan up`, the gateway and the control API refuse to start with empty or old default secrets.
- **Dev-only bypass:** `NIYAN_ALLOW_INSECURE_DEFAULTS=1` (exactly `1`, loud warning; not in the release Compose files).

Gateway keys are read-only in the Admin UI. Rotate with `niyan secrets rotate gateway-key`, then `niyan up`; read it with `niyan gateway keys --plain`. Upgrading from an install with shared defaults, Langfuse key handling and the Compose project name: [docs/secrets.md](docs/secrets.md).

## Start

```bash
niyan doctor
niyan up --build      # first start; plain `niyan up` afterwards for config-only changes
niyan status          # also prints the repo root it uses (and why) and the Compose project
```

Repo-local fallback (no shell init): `./niyan.sh …` or `.\niyan.cmd …`

| | |
|---|---|
| Admin UI | http://127.0.0.1:3080 (`admin` / password from `niyan secrets show`) |
| Gateway (OpenAI API) | http://127.0.0.1:4000 — Swagger at `/docs` |
| Control API | http://127.0.0.1:8100 |
| Gateway API key | generated per install — `niyan gateway keys --plain` (export as `NIYAN_API_KEY`) |

```bash
export NIYAN_API_KEY="$(niyan gateway keys --plain | head -1)"
```

Pull local models (Mac/Windows: host Ollama; Linux: Compose):

```bash
niyan model pull llama3.2:3b
niyan embeddings pull
```

Optional cloud models: Admin → **Providers** (paste key) → **Models → Proprietary** (enable). Same gateway. Details: [docs/quickstart.md](docs/quickstart.md).

## Updating (git pull, branch switch, local code changes)

`niyan up` reuses already-built images; it does **not** rebuild. After any of
these, rebuild:

- `git pull` / `git checkout <branch>` / editing `services/`, `api/`, `admin-ui/`
- re-running `./install.sh` (it never builds or starts containers)

```bash
git pull                       # or: git checkout <branch>
./install.sh                   # only if install.sh / cli/ / secrets changed; safe to re-run
niyan up --build               # rebuild gateway, niyan-api, admin-ui, guardrails, loadtest
niyan status
```

Config-only changes (Admin UI saves, `niyan model enable`, provider keys) need
plain `niyan up` (no rebuild). `niyan up` warns when an image is missing or
older than this checkout's HEAD commit.

Old builds shipped shared default secrets. With Docker running,
`git pull && ./install.sh && niyan up --build` rotates them in place and keeps
your data. Details: [docs/secrets.md](docs/secrets.md).

### Check that the running stack matches this checkout

```bash
niyan status                                     # prints repo root (and why) + Compose project
docker images --format '{{.Repository}} {{.CreatedAt}}' | grep '^niyan-'
git log -1 --format='%h %cd'                     # images must be newer than this commit
```

If the repo root is not this checkout, or the images are older than the commit,
run `niyan up --build` from this checkout (see "Two checkouts on one machine").

## Two checkouts on one machine

`niyan-local` and `niyan-complete` use **different Compose projects** (`niyan`
and `niyan-complete`), so their containers, images and volumes are separate.
They still publish the **same ports** (3080, 4000, 8100, …): run only one at a
time. The pull-only `~/.niyan` install also uses project `niyan`.

Installs made before `NIYAN_COMPOSE_PROJECT` existed keep running as `niyan`
(an existing `.env` without the key means `niyan`), so nothing is orphaned. Set
`NIYAN_COMPOSE_PROJECT=<name>` in `.env` to choose explicitly; see
[docs/secrets.md](docs/secrets.md#compose-project-name) before changing it on a
stack that already has data.

The `niyan` command targets the repo in `NIYAN_ROOT` (then `NIYAN_HOME`, then the
current directory). `./install.sh` rewrites the single `# >>> niyan initialize >>>`
block in your shell profile, so new shells follow the **last repo you installed**.
Shells that were already open keep the old value. `niyan status` shows which
root it picked and why.

Switch repos explicitly:

```bash
niyan down                                 # stop the other checkout's stack
cd ~/path/to/niyan-complete
./niyan.sh up --build                      # ./niyan.sh always targets its own checkout
# or, for this shell only:
export NIYAN_ROOT="$PWD" NIYAN_HOME="$PWD"; niyan up --build
# or permanently: ./install.sh (or niyan shell init) from this checkout, then open a new shell
```

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
niyan up --pull            # pull-only installs pull images instead of building
niyan uninstall            # removes ~/.niyan (remote CLI)
```

The pull-only installer replaces this checkout's shell block and uses Compose project `niyan` and the same ports; run `./install.sh` again here to switch back.

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
| [docs/secrets.md](docs/secrets.md) | Secrets, upgrades from shared defaults, Compose project name |
| [docs/remote-install.md](docs/remote-install.md) | GHCR / beta pull-only path |
| [docs/CHARTER.md](docs/CHARTER.md) | Local-only scope |

## License

Copyright 2026 Niyan Lab.

Licensed under the [Apache License, Version 2.0](LICENSE). Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
