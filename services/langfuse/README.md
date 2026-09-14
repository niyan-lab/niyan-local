# Langfuse

Self-hosted via `langfuse/langfuse:2` + Postgres in Compose (`obs` profile).

After first boot:

1. Open http://localhost:3100 (bundled Niyan Langfuse; avoids clash with a host Langfuse on :3000)
2. Create a user/project
3. Copy public + secret keys into `niyan.yaml` → `observability.public_key` / `secret_key`
4. Recreate gateway/litellm so env picks up keys (or set `LANGFUSE_*` in `.env`)

Override host port with `LANGFUSE_PORT` in `.env`.

**Reuse an existing Langfuse (e.g. already on :3000):** set `observability.enabled: false` to skip the Compose `obs` profile, or point gateway env `LANGFUSE_HOST` at `http://host.docker.internal:3000` with your existing project keys.

Disable with `observability.enabled: false` if laptop RAM is tight.
