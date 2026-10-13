# Remote install (Anaconda-style, pull-only)

Testers never clone this monorepo. They run a bash installer that writes `~/.niyan`, pulls **public** dependency images (Redis, LiteLLM, Langfuse, …) plus **private** prebuilt Niyan wrapper images, and installs a thin `niyan` CLI (`up` / `down` / `status` / `logs` / `doctor`).

Access control for the cohort: **private GHCR** + how you share the installer URL and a read-only `docker login` PAT. No license keys.

---

## Owner checklist (build → ship to beta testers)

Do these in order on your machine / GitHub. This is the full operator path.

### Prerequisites (you)

- Private GitHub repo with this codebase
- Docker Desktop (or Engine) locally for smoke tests
- Permission to create **GitHub Packages (GHCR)** and set them **private**
- A place to host two files privately: `install.sh` and `niyan-bundle-0.1.0.tgz` (Drive, Dropbox, private CDN, signed S3 URL)
- Optional: a short page on your website with the curl install command

### A. One-time: registry + credentials

1. Confirm your GitHub org/user slug (images become `ghcr.io/<owner>/niyan-*`).  
   Default in compose/bundle is `ghcr.io/intelligentindia7`. If your owner differs, set:
   ```bash
   export NIYAN_IMAGE_REGISTRY=ghcr.io/<your-owner>
   ```
   and stamp that into `bootstrap/stack/.env.example` before packing (or pass it to the installer).

2. Create a **read-only** PAT for testers:
   - GitHub → Settings → Developer settings → Personal access tokens  
   - Classic: enable **`read:packages` only**  
   - Save it in a password manager — you will email it (not put it on the public website)

3. (Recommended) Log in locally so you can smoke-test pulls:
   ```bash
   echo '<YOUR_READ_OR_WRITE_PAT>' | docker login ghcr.io -u <YOUR_GITHUB_USER> --password-stdin
   ```

### B. Build and push private Niyan images

1. Commit/push the release workflow and compose (this repo).
2. GitHub → **Actions → Release Niyan images → Run workflow**
3. Tag input: `0.1.0` (use the same tag everywhere below)
4. Wait until all six jobs succeed:  
   `niyan-gateway`, `niyan-api`, `niyan-admin-ui`, `niyan-guardrails`, `niyan-nemo`, `niyan-loadtest`
5. GitHub → **Packages** → open each package → **Package settings → Change visibility → Private**

### C. Pack the remote bundle

From the repo root:

```bash
cd niyan-local
export NIYAN_IMAGE_TAG=0.1.0
# if needed:
# export NIYAN_IMAGE_REGISTRY=ghcr.io/<your-owner>
chmod +x scripts/pack_remote_bundle.sh bootstrap/install.sh bootstrap/bin/niyan
./scripts/pack_remote_bundle.sh 0.1.0
# → dist/niyan-bundle-0.1.0.tgz
```

### D. Publish installer artifacts (private)

Upload / host:

| File | Source | Purpose |
|------|--------|---------|
| `install.sh` | [bootstrap/install.sh](../bootstrap/install.sh) | `curl \| bash` entrypoint |
| `niyan-bundle-0.1.0.tgz` | `dist/niyan-bundle-0.1.0.tgz` | stack + thin CLI (no app source) |

Get two HTTPS URLs (Drive “anyone with link”, signed URL, etc.). Prefer links that are not indexed publicly for long.

### E. Website snippet

```bash
# Testers: log in to GHCR first (credentials from invite email), then:
export NIYAN_BUNDLE_URL='https://YOUR_HOST/niyan-bundle-0.1.0.tgz'
export NIYAN_IMAGE_TAG=0.1.0
# export NIYAN_IMAGE_REGISTRY=ghcr.io/<your-owner>   # if not the default
curl -fsSL https://YOUR_HOST/install.sh | bash
```

Do **not** put the GHCR PAT on the website.

### F. Invite email (per tester)

Include:

1. Link to the install page / the curl commands above  
2. Docker login:
   ```bash
   echo '<READ_ONLY_PAT>' | docker login ghcr.io -u <YOUR_GITHUB_USER> --password-stdin
   ```
3. After install:
   ```bash
   source ~/.zshrc   # or ~/.bashrc
   niyan doctor
   niyan up
   ```
4. URLs: Admin http://127.0.0.1:3080 (`admin` / `niyan`) · Gateway http://127.0.0.1:4000  
5. Mac/Windows: install [Ollama](https://ollama.com) on the host; pull a model (`ollama pull llama3.2:3b`) or use Admin → Models  

### G. Smoke-test yourself before sending invites

```bash
# From repo (local bundle, no upload needed)
export NIYAN_HOME=/tmp/niyan-smoke
export NIYAN_PULL_ON_INSTALL=0   # set 1 after images exist in GHCR
./bootstrap/install.sh
export PATH="$NIYAN_HOME/bin:$PATH"
niyan doctor
# after GHCR images are private + docker login:
# NIYAN_PULL_ON_INSTALL=1 ./bootstrap/install.sh
# niyan up
```

Or full path mimicking testers: host the tarball, set `NIYAN_BUNDLE_URL`, run the published `install.sh`.

### H. Track the cohort

Keep a private sheet: name, email, date invited, PAT rotated?, issues.

If someone leaves: revoke/rotate the read-only PAT and issue a new one to remaining testers.

---

## Tester flow (summary)

```bash
echo '<PAT>' | docker login ghcr.io -u <user> --password-stdin
export NIYAN_BUNDLE_URL='https://…/niyan-bundle-0.1.0.tgz'
curl -fsSL https://…/install.sh | bash
source ~/.zshrc   # or new terminal
niyan doctor
niyan up
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

Uninstall also removes the `# >>> niyan initialize >>>` block from your shell rc.

---

## Repo layout (what we ship)

| Path | Role |
|------|------|
| [deploy/docker-compose.release.yml](../deploy/docker-compose.release.yml) | Image-only compose (source of truth for packing) |
| [bootstrap/](../bootstrap/) | Bundle contents: `bin/niyan`, `stack/`, `install.sh` |
| [bootstrap/install.sh](../bootstrap/install.sh) | Pull-only installer (`curl \| bash` or from this checkout) |
| [scripts/pack_remote_bundle.sh](../scripts/pack_remote_bundle.sh) | Build `dist/niyan-bundle-*.tgz` |
| [.github/workflows/release-images.yml](../.github/workflows/release-images.yml) | Build/push wrapper images to GHCR |

From-source installs use root [install.sh](../install.sh) / [uninstall.sh](../uninstall.sh) (venv + full Python CLI + local Compose build).

---

## Notes

- Default starter profiles: `admin`, `obs`, `guard-llm`; host-Ollama overlay on Darwin; `ollama` profile on Linux.
- LiteLLM routes start from the baked `services/litellm/config.generated.yaml` in the bundle. Advanced model/config changes for beta are via Admin UI where supported, or ask you for a new bundle.
- Change `NIYAN_IMAGE_REGISTRY` / `NIYAN_IMAGE_TAG` in `~/.niyan/stack/.env` to retarget pulls without reinstalling.
