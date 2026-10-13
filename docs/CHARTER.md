# Niyan Local — charter

**`niyan-local` is local deployment only:** Docker Compose, installers (`install.sh` / `install.ps1`), uninstallers (`uninstall.sh` / `uninstall.ps1`), CLI, bootstrap/remote-install, and on-machine GHCR pull.

## In scope

- Compose stack + profiles (admin, obs, vectors, ollama, guardrails)
- `niyan` CLI and thin bash remote installer
- Gateway / niyan-api / admin-ui for VM + Docker Desktop
- Docs for quickstart, remote install, architecture (Compose)

## Out of scope

- **Kubernetes** — Helm, Terraform, cluster lifecycle CI, Ingress recipes
- Those live in [`niyan-complete`](https://github.com/niyan-lab/niyan-complete)

## Lineage

Seeded from orphan import `c5906a9` (*Initial import of niyan local stack*, 2026-09-14), curated from the `cursor/novus-slm-stack` Compose line. Later K8s work on complete must **not** be copied here.

Product improvements that apply to Compose (runtime config, install polish, UI) are backported from complete — see `docs/SYNC.md`.
