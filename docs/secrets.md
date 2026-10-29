# Secrets (Compose / VM installs)

There are no shared default credentials. On first run `install.sh` / `install.ps1` (via `niyan secrets init`) generate:

- `niyan.yaml`: `admin_auth.password`, `admin_auth.jwt_secret`, `proxy.api_keys` (gateway / LiteLLM master key). This is the single source for these three, for both the from-source and the pull-only installer (which mirrors them into `~/.niyan/stack/.env` for Compose).
- `.env`: `POSTGRES_PASSWORD`, `LANGFUSE_NEXTAUTH_SECRET`, `LANGFUSE_SALT`, `LANGFUSE_ENCRYPTION_KEY`.

Re-running the installer keeps existing strong values. The admin password is printed at the end of an install that generated it (it then sits in your terminal scrollback — clear it on shared screens); later use `niyan secrets show` (`--all` adds the API key and JWT secret, `--field password` prints one raw value for scripts). `niyan up`, the gateway and the control API refuse to start with empty or old default secrets. For throwaway dev/tests only, `NIYAN_ALLOW_INSECURE_DEFAULTS=1` (exactly `1`) bypasses that check with a loud warning; it is not wired into the release/pull-only Compose files. LiteLLM and Langfuse do not check their own secrets — the `niyan up` pre-check (and `~/.niyan/bin/niyan up` for pull-only installs) is what guards them. Secrets are never stored in Postgres/Redis; `/api/config` returns them masked.

**Gateway keys are read-only in the Admin UI** (the save endpoints return 409 for a changed key), so the Gateway page always shows the key the gateway enforces. To rotate: `niyan secrets rotate gateway-key` (pull-only: `~/.niyan/bin/niyan secrets rotate gateway-key`), then `niyan up`. Read the new key with `niyan gateway keys --plain`.

## Upgrading from an older install (shared default secrets)

Builds before per-install secrets shipped `niyan` / `sk-niyan-local` / `change-me…` defaults. Just pull and re-run the installer — **with Docker running**:

```bash
git pull && ./install.sh
niyan up --build
niyan secrets show              # new admin password
```

Pull-only installs: re-run the bootstrap installer, then `niyan up --pull`.

What happens, without wiping data:

- **Postgres** (`<project>_niyan_pg` volume exists, `niyan_niyan_pg` for project `niyan`): a new password is applied in place with `ALTER USER` (over the container's local socket), verified over TCP, then written to `.env`. `niyan up` recreates containers with it.
- **Langfuse** `LANGFUSE_NEXTAUTH_SECRET` is rotated (only logs users out). `LANGFUSE_SALT` / `LANGFUSE_ENCRYPTION_KEY` are rotated only if no Langfuse rows depend on them (API keys / stored LLM keys). Otherwise (a **confirmed** non-zero count) the old public value is **kept**, marked `NIYAN_LEGACY_LANGFUSE_SALT=1` / `NIYAN_LEGACY_LANGFUSE_ENCRYPTION_KEY=1` in `.env`, and the installer warns: anyone with repo access knows that key. Marked keys are re-counted on every install and rotated as soon as nothing depends on them. If the count itself fails (Postgres restarting, exec error/timeout) it is retried 3× with backoff; if it still fails the installer stops **before changing anything** (no marker, no rotation) and `niyan up` keeps refusing until you re-run the installer. A missing `langfuse` database counts as 0 rows. The Langfuse counts run before the Postgres password is rotated.
- **Admin password, JWT secret, gateway key** in `niyan.yaml` are regenerated. Old secrets stored in the Postgres config table are scrubbed on API start and an admin-UI save cannot write a default back. Update clients that used `sk-niyan-local` to `niyan gateway keys --plain`.
- **Docker not running**: the installer refuses (exit 2) and changes nothing, because it cannot tell whether data exists.

```bash
export NIYAN_API_KEY="$(niyan gateway keys --plain | head -1)"
```

## Compose project name

Containers, built images (`<project>-<service>`) and volumes (`<project>_niyan_pg`, …)
are scoped by the Compose project. The CLI picks it in this order:

1. `NIYAN_COMPOSE_PROJECT` in the environment
2. `NIYAN_COMPOSE_PROJECT=` in this checkout's `.env`
3. an existing `.env` without that key: `niyan` (installs from before the key existed)
4. otherwise the repo default (`niyan` for niyan-local, `niyan-complete` for niyan-complete), written to `.env` by `./install.sh` from `.env.example`

`niyan status` prints the project and where it came from.

**Moving an existing stack to a new project name** (for example an older
niyan-complete install still on `niyan`, so it no longer clashes with
niyan-local). Changing the name alone starts with empty volumes; copy the data
first. With the stack stopped (`niyan down`):

```bash
NEW=niyan-complete
for v in niyan_pg niyan_qdrant niyan_ollama; do      # plus any other <old>_* volumes you use
  docker volume inspect "niyan_$v" >/dev/null 2>&1 || continue
  docker volume create "${NEW}_$v" >/dev/null
  docker run --rm -v "niyan_$v:/from:ro" -v "${NEW}_$v:/to" alpine sh -c 'cp -a /from/. /to/'
done
echo "NIYAN_COMPOSE_PROJECT=$NEW" >> .env
niyan up --build
```

Keep the old `niyan_*` volumes until the new stack is verified; remove them by
hand afterwards. The Postgres password in `.env` is unchanged, so it still
matches the copied data.
