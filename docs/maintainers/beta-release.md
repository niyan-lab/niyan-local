# Beta release (maintainers)

Build the private GHCR images and the pull-only bundle that [../remote-install.md](../remote-install.md) installs.

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
   - Save it in a password manager — share it privately (never on the public website)

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
| `install.sh` | [bootstrap/install.sh](../../bootstrap/install.sh) | `curl \| bash` entrypoint |
| `niyan-bundle-0.1.0.tgz` | `dist/niyan-bundle-0.1.0.tgz` | stack + thin CLI (no app source) |

Get two HTTPS URLs (Drive “anyone with link”, signed URL, etc.). Prefer links that are not indexed publicly for long.

### E. Website snippet

```bash
# Testers: docker login ghcr.io first (read-only token), then:
export NIYAN_BUNDLE_URL='https://YOUR_HOST/niyan-bundle-0.1.0.tgz'
export NIYAN_IMAGE_TAG=0.1.0
# export NIYAN_IMAGE_REGISTRY=ghcr.io/<your-owner>   # if not the default
curl -fsSL https://YOUR_HOST/install.sh | bash
```

Do **not** put the GHCR PAT on the website.

### F. Smoke-test before sharing

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
