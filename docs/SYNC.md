# Syncing from `niyan-complete`

Source of truth for **Compose-relevant** product code: `niyan-lab/niyan-complete` `dev`.

## Never copy into this repo

- `deploy/helm/**`
- `deploy/terraform/**`
- `deploy/ci/**`
- `.github/workflows/niyan-lifecycle.yml`
- K8s-only docs and `api/requirements-k8s.txt`

## Next backport (Phase 1)

Postgres runtime config + Redis gateway cache + Compose always-on Postgres (gateway `runtime_config`, api `config_store` / Docker orchestrator). Full map lives in the NiyanAI Project store: `docs/niyan-local-sync.md`.

## Rules

1. Prefer small PRs to `dev`.
2. Strip Kubernetes wording from any README/docs cherry-picks.
3. Do not reintroduce Novus naming (`shell/novus.sh`, `NOVUS_*`).
