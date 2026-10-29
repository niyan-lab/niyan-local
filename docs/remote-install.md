# Remote install (Anaconda-style, pull-only)

Testers never clone this repo. They run a bash installer that writes `~/.niyan`, pulls **public** dependency images (Redis, LiteLLM, Langfuse, …) plus **private** prebuilt Niyan wrapper images, and installs a thin `niyan` CLI (`up` / `down` / `status` / `logs` / `doctor`).

Access: **private GHCR** images; you get the installer URL and a read-only `docker login` token from the maintainers. No license keys.

---

## Tester flow (summary)

```bash
echo '<PAT>' | docker login ghcr.io -u <user> --password-stdin
export NIYAN_BUNDLE_URL='https://…/niyan-bundle-0.1.0.tgz'
curl -fsSL https://…/install.sh | bash
source ~/.zshrc   # or new terminal
niyan doctor
niyan up --pull
```

| Command | What it does |
|---------|----------------|
| `niyan doctor` | Docker + Compose + stack files (+ host Ollama on Mac) |
| `niyan up` | `docker compose up -d` (pull-only images) |
| `niyan up --pull` | Pull then up |
| `niyan status` | Compose `ps` |
| `niyan logs [-f] [svc]` | Logs |
| `niyan down` | Stop stack |
| `niyan uninstall` | Stop stack, unwire PATH, delete `~/.niyan` |
| `niyan uninstall --volumes` | Same, and delete Docker volumes |
| `niyan uninstall --volumes` | Same, and delete Docker volumes |

Uninstall also removes the `# >>> niyan initialize >>>` block from your shell rc.

**Source checkout on the same machine?** The pull-only installer writes the same `# >>> niyan initialize >>>` block (`NIYAN_ROOT=~/.niyan/stack`) and uses Compose project `niyan` and the same ports. Re-run `./install.sh` in the checkout to switch back, and run only one stack at a time.

---

## Repo layout (what we ship)

| Path | Role |
|------|------|
| [deploy/docker-compose.release.yml](../deploy/docker-compose.release.yml) | Image-only compose (source of truth for packing) |
| [bootstrap/](../bootstrap/) | Bundle contents: `bin/niyan`, `stack/`, `install.sh` |
| [bootstrap/install.sh](../bootstrap/install.sh) | Pull-only installer (`curl \| bash` or from this checkout) |
| [scripts/pack_remote_bundle.sh](../scripts/pack_remote_bundle.sh) | Build `dist/niyan-bundle-*.tgz` |
| [.github/workflows/release-images.yml](../.github/workflows/release-images.yml) | Build/push wrapper images to GHCR |

From-source installs use root [install.sh](../install.sh) / [uninstall.sh](../uninstall.sh) (venv + full Python CLI); `install.sh` never builds or starts containers. Images are built locally by `niyan up --build`.

---

## Notes

- Default starter profiles: `admin`, `obs`, `guard-llm`; host-Ollama overlay on Darwin; `ollama` profile on Linux.
- LiteLLM routes start from the baked `services/litellm/config.generated.yaml` in the bundle. Advanced model/config changes for beta are via Admin UI where supported, or ask the maintainers for a new bundle.
- Change `NIYAN_IMAGE_REGISTRY` / `NIYAN_IMAGE_TAG` in `~/.niyan/stack/.env` to retarget pulls without reinstalling.

Maintainers: building and publishing the images/bundle is in [maintainers/beta-release.md](maintainers/beta-release.md).
