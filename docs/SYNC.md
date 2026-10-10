# Syncing from `niyan-complete`

Source of truth for **Compose-relevant** product code: `niyan-lab/niyan-complete` `dev`.

## Never copy into this repo

- `deploy/helm/**`
- `deploy/terraform/**`
- `deploy/ci/**`
- `.github/workflows/niyan-lifecycle.yml`
- K8s-only docs and `api/requirements-k8s.txt`
- `KubernetesOrchestrator` / `kubernetes` Python client

## Status

| Phase | Status |
|-------|--------|
| 0 — charter (`CHARTER.md`) | Done (PR #1 → `6f7bdcd`) |
| 1+ — runtime config, Compose Postgres/Redis, admin-ui, API Docker path | This branch — backported from complete `dev` @ `93c8117`, K8s omitted |

Local always resolves `NIYAN_PLATFORM=vm` and uses `DockerOrchestrator` only.

## Rules

1. Prefer small PRs to `dev`.
2. Strip Kubernetes wording from any README/docs cherry-picks.
3. Do not reintroduce Novus naming (`shell/novus.sh`, `NOVUS_*`).
4. Full map: NiyanAI Project store `docs/niyan-local-sync.md`.
