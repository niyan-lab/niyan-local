"""Niyan CLI entrypoint."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from niyan import __version__
from niyan.client import NiyanApiClient
from niyan.config import (
    GuardrailsProvider,
    ModelProvider,
    VectorProvider,
    load_config,
    save_config,
)
from niyan.doctor import detect_profile, run_doctor
from niyan.local_compose import InsecureSecretsError, find_repo_root, recreate_litellm, stack_down, stack_logs, stack_up
from niyan.secrets_init import ensure_secrets
from niyan.shell_init import detect_shell, init_shell
from niyan.uninstall import run_uninstall

app = typer.Typer(
    name="niyan",
    help="Niyan — Anaconda-style SLM stack manager (Ollama + LiteLLM + Langfuse + guardrails + vectors).",
    no_args_is_help=True,
)
model_app = typer.Typer(help="Manage local and proprietary models")
guardrails_app = typer.Typer(help="Configure guardrails")
vector_app = typer.Typer(help="Configure vector store")
embeddings_app = typer.Typer(help="Configure embeddings")
gateway_app = typer.Typer(help="Gateway / API key helpers")
config_app = typer.Typer(help="Show or mutate niyan.yaml")
shell_app = typer.Typer(help="Shell integration (like `conda init`)")
provider_app = typer.Typer(help="Configure OpenAI / Gemini / Anthropic API keys")
secrets_app = typer.Typer(help="Generate or show per-install secrets (.env / niyan.yaml)")

app.add_typer(model_app, name="model")
app.add_typer(guardrails_app, name="guardrails")
app.add_typer(vector_app, name="vector")
app.add_typer(embeddings_app, name="embeddings")
app.add_typer(gateway_app, name="gateway")
app.add_typer(config_app, name="config")
app.add_typer(shell_app, name="shell")
app.add_typer(provider_app, name="provider")
app.add_typer(secrets_app, name="secrets")

console = Console()


def _repo() -> Path:
    return find_repo_root()


def _config_path(repo: Path) -> Path:
    return repo / "niyan.yaml"


def _load(repo: Path):
    path = _config_path(repo)
    if not path.exists():
        console.print("[yellow]niyan.yaml missing — run `niyan init` first[/yellow]")
        raise typer.Exit(1)
    return load_config(path)


def _api(repo: Path, login: bool = False) -> NiyanApiClient:
    cfg = _load(repo)
    client = NiyanApiClient(base_url=f"http://127.0.0.1:{cfg.api.port}")
    if login and client.healthy():
        try:
            client.login(cfg.admin_auth.username, cfg.admin_auth.password)
        except Exception:
            pass
    return client


@app.command()
def version() -> None:
    """Print CLI version."""
    console.print(f"niyan {__version__}")


@app.command()
def init(
    force: bool = typer.Option(False, "--force", help="Overwrite existing niyan.yaml"),
    shell: bool = typer.Option(
        False,
        "--shell",
        help="Also run `niyan shell init` (wire `niyan` into ~/.bashrc or ~/.zshrc)",
    ),
) -> None:
    """Create niyan.yaml from the example config."""
    repo = _repo()
    dest = _config_path(repo)
    example = repo / "configs" / "niyan.example.yaml"
    if dest.exists() and not force:
        console.print(f"[yellow]{dest} already exists (use --force to overwrite)[/yellow]")
    else:
        if not example.exists():
            console.print(f"[red]Missing example config at {example}[/red]")
            raise typer.Exit(1)
        shutil.copy(example, dest)
        env_example = repo / ".env.example"
        env_dest = repo / ".env"
        if env_example.exists() and not env_dest.exists():
            shutil.copy(env_example, env_dest)
        console.print(f"[green]Wrote {dest}[/green]")
    if dest.exists():
        _print_secrets_report(ensure_secrets(repo))
    if shell:
        action, rc = init_shell(repo)
        console.print(f"[green]Shell {action}:[/green] {rc}")
        console.print("Restart the shell or run: [cyan]source {rc}[/cyan]".format(rc=rc))
    console.print("Next: `niyan doctor` then `niyan up`")


@shell_app.command("init")
def shell_init(
    shell: Optional[str] = typer.Option(
        None,
        "--shell",
        "-s",
        help="bash, zsh, fish, or powershell (default: detect from OS / $SHELL)",
    ),
    reverse: bool = typer.Option(
        False,
        "--reverse",
        help="Remove the Niyan block from the shell rc file",
    ),
) -> None:
    """Add Niyan to PATH via your shell profile (like `conda init`).

    Writes a marked block to ~/.zshrc, ~/.bashrc, or your PowerShell profile that
    sets NIYAN_ROOT and sources shell/niyan.sh (or shell/niyan.ps1) so `niyan`
    works from any directory.
    """
    repo = _repo()
    sh = detect_shell(shell)
    action, rc = init_shell(repo, shell=sh, reverse=reverse)
    if reverse:
        if action == "removed":
            console.print(f"[green]Removed Niyan block from[/green] {rc}")
        else:
            console.print(f"[yellow]No Niyan block found in[/yellow] {rc}")
        return
    console.print(f"[green]Shell {action}:[/green] {rc} ([cyan]{sh}[/cyan])")
    console.print(f"  NIYAN_ROOT={repo}")
    console.print("Open a new terminal, or run:")
    if sh == "powershell":
        console.print(f"  [cyan]. \"{rc}\"[/cyan]")
    else:
        console.print(f"  [cyan]source {rc}[/cyan]")
    console.print("Then: [cyan]niyan doctor[/cyan]")


@shell_app.command("hook")
def shell_hook(
    shell: Optional[str] = typer.Option(None, "--shell", "-s"),
) -> None:
    """Print the shell block that `niyan shell init` would install (for debugging)."""
    from niyan.shell_init import build_block

    repo = _repo()
    sh = detect_shell(shell)
    console.print(build_block(repo, sh), end="")


@app.command()
def doctor() -> None:
    """Detect profile and check Docker / Ollama prerequisites."""
    repo = _repo()
    path = _config_path(repo)
    cfg = load_config(path) if path.exists() else None
    report = run_doctor(cfg, repo)
    console.print(f"[bold]Resolved profile:[/bold] {report.resolved_profile.value}")
    table = Table(title="Niyan doctor")
    table.add_column("Check")
    table.add_column("OK")
    table.add_column("Detail")
    for c in report.checks:
        table.add_row(c.name, "[green]yes[/green]" if c.ok else "[red]no[/red]", c.detail)
    console.print(table)
    if not report.ok:
        raise typer.Exit(1)


@app.command("up")
@app.command("install")
def up(
    build: bool = typer.Option(
        False,
        "--build",
        help="Rebuild images before starting (gateway, niyan-api, admin-ui, …).",
    ),
) -> None:
    """Bring up the Niyan stack via Docker Compose."""
    repo = _repo()
    cfg = _load(repo)
    profile = detect_profile(cfg.profile)
    console.print(f"Starting Niyan with profile [cyan]{profile.value}[/cyan] …")
    if build:
        console.print("[dim]Rebuilding images (--build)…[/dim]")
    if profile.value in {"mac", "windows"}:
        console.print(
            f"[dim]{profile.value}: using host Ollama at host.docker.internal:11434[/dim]"
        )
    try:
        stack_up(repo, cfg, build=build)
    except InsecureSecretsError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    console.print("[green]Stack starting.[/green]")
    console.print(f"  Proxy (OpenAI):  http://127.0.0.1:{cfg.proxy.port}/v1/chat/completions")
    console.print(f"  Proxy Swagger:   http://127.0.0.1:{cfg.proxy.port}/docs")
    console.print(f"  Control plane:   http://127.0.0.1:{cfg.api.port}/docs")
    if cfg.admin.enabled:
        console.print(f"  Admin console:   http://127.0.0.1:{cfg.admin.port}")
    if cfg.observability.enabled:
        import os

        langfuse_port = os.environ.get("LANGFUSE_PORT", "3100")
        console.print(f"  Langfuse:        http://127.0.0.1:{langfuse_port}")
        console.print(
            "  [dim](bundled Langfuse uses :3100 by default so it does not clash with an existing :3000 stack)[/dim]"
        )
    if cfg.embeddings.enabled:
        console.print(f"  Embeddings:      model={cfg.embeddings.model} via /v1/embeddings")
    if cfg.vector.enabled:
        console.print(f"  Vector store:    provider={cfg.vector.provider.value}")
        if cfg.vector.provider.value == "qdrant":
            console.print(f"  Qdrant UI/API:   http://127.0.0.1:{cfg.vector.qdrant.port}")
    console.print("Run `niyan status` to check health.")


@app.command("down")
@app.command("stop")
def down() -> None:
    """Stop the Niyan stack."""
    repo = _repo()
    cfg = _load(repo)
    stack_down(repo, cfg)
    console.print("[green]Stack stopped.[/green]")


@app.command()
def uninstall(
    volumes: bool = typer.Option(
        False,
        "--volumes",
        help="Also delete Docker volumes (Postgres, Redis, …).",
    ),
    keep_config: bool = typer.Option(
        False,
        "--keep-config",
        help="Keep niyan.yaml and .env in the checkout.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not prompt."),
) -> None:
    """Stop the stack, unwire the shell, and remove the local venv.

    Does not delete the git checkout. Prefer `./uninstall.sh` from the repo root.
    """
    repo = _repo()
    if not yes:
        prompt = "Stop Niyan, remove the shell hook, and delete .venv"
        if volumes:
            prompt += " (including Docker volumes)"
        if not typer.confirm(f"{prompt}?", default=False):
            raise typer.Abort()
    for line in run_uninstall(repo, volumes=volumes, keep_config=keep_config):
        console.print(f"  {line}")
    console.print("[green]Uninstalled.[/green] Reinstall with ./install.sh or .\\install.ps1")


@app.command()
def status() -> None:
    """Show service health (API if up, else compose ps)."""
    repo = _repo()
    cfg = _load(repo)
    client = _api(repo, login=True)
    if client.healthy():
        try:
            data = client.get("/api/services")
            table = Table(title="Niyan services")
            table.add_column("Service")
            table.add_column("Status")
            table.add_column("Detail")
            for svc in data.get("services", []):
                ok = svc.get("healthy") or svc.get("status") == "running"
                table.add_row(
                    svc.get("name", "?"),
                    "[green]up[/green]" if ok else "[red]down[/red]",
                    svc.get("detail", svc.get("status", "")),
                )
            console.print(table)
            return
        except Exception as exc:
            console.print(f"[yellow]API reachable but services call failed: {exc}[/yellow]")

    console.print("[dim]Control plane not ready — showing docker compose ps[/dim]")
    import subprocess

    from niyan.local_compose import build_env, compose_cmd

    profile = detect_profile(cfg.profile)
    cmd = compose_cmd(repo, profile, cfg) + ["ps"]
    env = build_env(repo, profile, cfg)
    subprocess.run(cmd, cwd=str(repo), env=env)


@app.command()
def logs(
    service: Optional[str] = typer.Argument(None, help="Optional service name"),
    follow: bool = typer.Option(False, "-f", "--follow"),
) -> None:
    """Tail container logs."""
    repo = _repo()
    cfg = _load(repo)
    stack_logs(repo, cfg, service, follow)


@model_app.command("list")
def model_list() -> None:
    """List configured and installed models."""
    repo = _repo()
    cfg = _load(repo)
    client = _api(repo, login=True)
    if client.healthy() and client.token:
        data = client.get("/api/models")
        table = Table(title="Models")
        table.add_column("ID")
        table.add_column("Provider")
        table.add_column("Family")
        table.add_column("Enabled")
        table.add_column("Installed")
        for m in data.get("models", []):
            table.add_row(
                m.get("id", ""),
                m.get("provider", "ollama"),
                m.get("family", ""),
                str(m.get("enabled")),
                str(m.get("installed")),
            )
        console.print(table)
    else:
        for m in cfg.models:
            console.print(
                f"{m.id} provider={m.provider.value} family={m.family} enabled={m.enabled}"
            )


def _pull_models(names: list[str]) -> None:
    """Pull models through Niyan (API → Ollama, or host Ollama CLI as fallback)."""
    if not names:
        console.print("[yellow]No models to pull[/yellow]")
        return
    repo = _repo()
    client = _api(repo, login=True)
    if client.healthy() and client.token:
        for n in names:
            console.print(f"Pulling {n} via Niyan …")
            client.post("/api/models/pull", {"name": n})
            console.print(f"[green]Pull requested: {n}[/green]")
        return

    import subprocess

    if shutil.which("ollama") is None:
        console.print(
            "[red]niyan-api not reachable and `ollama` not on PATH — "
            "start the stack (`niyan up`) or install Ollama on the host[/red]"
        )
        raise typer.Exit(1)
    for n in names:
        console.print(f"Pulling {n} via Niyan (host Ollama) …")
        subprocess.run(["ollama", "pull", n], check=False)


@model_app.command("enable")
def model_enable(name: str = typer.Argument(..., help="Model id to enable")) -> None:
    """Enable a model (proprietary requires provider API key)."""
    repo = _repo()
    path = _config_path(repo)
    cfg = _load(repo)
    target = next((m for m in cfg.models if m.id == name), None)
    if target is None:
        console.print(f"[red]Unknown model: {name}[/red]")
        raise typer.Exit(1)
    if not cfg.provider_ready(target.provider):
        console.print(
            f"[red]Provider {target.provider.value} not configured — "
            f"run: niyan provider set {target.provider.value} --api-key …[/red]"
        )
        raise typer.Exit(1)
    target.enabled = True
    save_config(path, cfg)
    recreate_litellm(repo, cfg)
    console.print(f"[green]Enabled {name}[/green] — LiteLLM refreshed")


@model_app.command("disable")
def model_disable(name: str = typer.Argument(..., help="Model id to disable")) -> None:
    """Disable a model in niyan.yaml and refresh LiteLLM."""
    repo = _repo()
    path = _config_path(repo)
    cfg = _load(repo)
    target = next((m for m in cfg.models if m.id == name), None)
    if target is None:
        console.print(f"[red]Unknown model: {name}[/red]")
        raise typer.Exit(1)
    target.enabled = False
    if not any(m.enabled for m in cfg.models):
        console.print("[red]At least one model must remain enabled[/red]")
        raise typer.Exit(1)
    save_config(path, cfg)
    recreate_litellm(repo, cfg)
    console.print(f"[green]Disabled {name}[/green] — LiteLLM refreshed")


@provider_app.command("set")
def provider_set(
    name: str = typer.Argument(..., help="openai, gemini, or anthropic"),
    api_key: str = typer.Option(..., "--api-key", help="Provider API key"),
    enabled: bool = typer.Option(True, "--enabled/--disabled", help="Enable provider"),
) -> None:
    """Store a proprietary provider API key in niyan.yaml."""
    if name not in {"openai", "gemini", "anthropic"}:
        console.print("[red]name must be openai, gemini, or anthropic[/red]")
        raise typer.Exit(1)
    repo = _repo()
    path = _config_path(repo)
    cfg = _load(repo)
    cred = getattr(cfg.providers, name)
    cred.api_key = api_key.strip()
    cred.enabled = enabled
    save_config(path, cfg)
    recreate_litellm(repo, cfg)
    console.print(f"[green]Provider {name} saved[/green] (enabled={enabled})")
    console.print("Enable models with: [cyan]niyan model enable claude-sonnet-5[/cyan]")


@provider_app.command("status")
def provider_status() -> None:
    """Show whether OpenAI / Gemini / Anthropic keys are configured (never prints full keys)."""
    repo = _repo()
    cfg = _load(repo)
    table = Table(title="Providers")
    table.add_column("Provider")
    table.add_column("Enabled")
    table.add_column("Configured")
    table.add_column("Last4")
    for pname in ("openai", "gemini", "anthropic"):
        cred = getattr(cfg.providers, pname)
        key = cred.api_key.strip()
        table.add_row(
            pname,
            str(cred.enabled),
            "yes" if key else "no",
            key[-4:] if len(key) >= 4 else "—",
        )
    console.print(table)


@model_app.command("pull")
def model_pull(name: Optional[str] = typer.Argument(None, help="Model tag; default=all enabled")) -> None:
    """Pull chat and embedding model(s) into Ollama via Niyan."""
    repo = _repo()
    cfg = _load(repo)
    if name:
        entry = next((m for m in cfg.models if m.id == name), None)
        if entry and entry.provider != ModelProvider.ollama:
            console.print(
                f"[yellow]{name} is proprietary — enable with "
                f"`niyan model enable {name}` (no pull)[/yellow]"
            )
            raise typer.Exit(0)
        names = [name]
    else:
        names = [m.id for m in cfg.enabled_models() if m.provider == ModelProvider.ollama]
        if cfg.embeddings.enabled and cfg.embeddings.model:
            if cfg.embeddings.model not in names:
                names.append(cfg.embeddings.model)
    _pull_models(names)


@model_app.command("remove")
@model_app.command("delete")
def model_remove(name: str) -> None:
    """Delete a model's weights from disk (Ollama) via Niyan."""
    repo = _repo()
    client = _api(repo, login=True)
    if not client.healthy() or not client.token:
        console.print("[red]niyan-api not reachable[/red]")
        raise typer.Exit(1)
    client.delete(f"/api/models/{name}")
    console.print(f"[green]Deleted {name} from disk[/green]")


@model_app.command("load")
def model_load(name: str) -> None:
    """Load a model into Ollama memory (keeps it resident until ejected)."""
    repo = _repo()
    client = _api(repo, login=True)
    if not client.healthy() or not client.token:
        console.print("[red]niyan-api not reachable[/red]")
        raise typer.Exit(1)
    console.print(f"Loading {name} into memory …")
    client.post(f"/api/models/{name}/load", {})
    console.print(f"[green]Loaded {name} into memory[/green]")


@model_app.command("eject")
def model_eject(name: str) -> None:
    """Unload a model from Ollama memory (keeps weights on disk)."""
    repo = _repo()
    client = _api(repo, login=True)
    if not client.healthy() or not client.token:
        console.print("[red]niyan-api not reachable[/red]")
        raise typer.Exit(1)
    client.post(f"/api/models/{name}/eject", {})
    console.print(f"[green]Ejected {name} from memory[/green] (still on disk)")


@guardrails_app.command("provider")
def guardrails_provider(
    provider: str = typer.Argument(..., help="llm_guard or nemo"),
) -> None:
    """Set active guardrails provider and recreate stack services."""
    if provider not in {"llm_guard", "nemo"}:
        console.print("[red]provider must be llm_guard or nemo[/red]")
        raise typer.Exit(1)
    repo = _repo()
    path = _config_path(repo)
    cfg = _load(repo)
    cfg.guardrails.provider = GuardrailsProvider(provider)
    save_config(path, cfg)
    console.print(f"[green]guardrails.provider={provider}[/green] — restarting stack …")
    stack_down(repo, cfg)
    stack_up(repo, cfg)


@vector_app.command("provider")
def vector_provider(
    provider: str = typer.Argument(..., help="qdrant or pgvector"),
) -> None:
    """Set active vector provider, enable vector store, and recreate stack."""
    if provider not in {"qdrant", "pgvector"}:
        console.print("[red]provider must be qdrant or pgvector[/red]")
        raise typer.Exit(1)
    repo = _repo()
    path = _config_path(repo)
    cfg = _load(repo)
    cfg.vector.provider = VectorProvider(provider)
    cfg.vector.enabled = True
    save_config(path, cfg)
    console.print(f"[green]vector.provider={provider}[/green] — restarting stack …")
    stack_down(repo, cfg)
    stack_up(repo, cfg)


@vector_app.command("enable")
def vector_enable(
    enabled: bool = typer.Argument(True, help="true/false"),
) -> None:
    """Enable or disable the vector store profile and recreate stack."""
    repo = _repo()
    path = _config_path(repo)
    cfg = _load(repo)
    cfg.vector.enabled = enabled
    save_config(path, cfg)
    console.print(f"[green]vector.enabled={enabled}[/green] — restarting stack …")
    stack_down(repo, cfg)
    stack_up(repo, cfg)


@embeddings_app.command("model")
def embeddings_model(
    name: str = typer.Argument("nomic-embed-text", help="Embedding model id (served via Ollama)"),
    pull: bool = typer.Option(False, "--pull", help="Also pull the model via Niyan"),
) -> None:
    """Set the embedding model id in niyan.yaml."""
    repo = _repo()
    path = _config_path(repo)
    cfg = _load(repo)
    cfg.embeddings.model = name
    cfg.embeddings.enabled = True
    save_config(path, cfg)
    console.print(f"[green]embeddings.model={name}[/green]")
    if pull:
        _pull_models([name])
    else:
        console.print(f"Pull with: [cyan]niyan embeddings pull[/cyan]")


@embeddings_app.command("pull")
def embeddings_pull(
    name: Optional[str] = typer.Argument(
        None,
        help="Embedding model id; default=embeddings.model from niyan.yaml",
    ),
) -> None:
    """Pull the embedding model via Niyan (internally Ollama) — same path as chat models."""
    repo = _repo()
    cfg = _load(repo)
    model = name or cfg.embeddings.model
    if not model:
        console.print("[red]No embedding model configured — set with `niyan embeddings model`[/red]")
        raise typer.Exit(1)
    if not cfg.embeddings.enabled and not name:
        console.print("[yellow]embeddings.enabled is false — pulling anyway[/yellow]")
    _pull_models([model])


@config_app.command("show")
def config_show() -> None:
    """Print niyan.yaml."""
    repo = _repo()
    console.print(_config_path(repo).read_text())


def _print_secrets_report(report: dict) -> None:
    if report["generated"]:
        console.print("[green]Generated secrets:[/green] " + ", ".join(report["generated"]))
    if report["kept"]:
        console.print("[dim]Kept existing secrets:[/dim] " + ", ".join(report["kept"]))
    for w in report["warnings"]:
        console.print(f"[yellow]warning:[/yellow] {w}")


@secrets_app.command("init")
def secrets_init() -> None:
    """Generate missing secrets into .env / niyan.yaml (chmod 600). Never overwrites real values."""
    repo = _repo()
    if not _config_path(repo).exists():
        console.print("[yellow]niyan.yaml missing — run `niyan init` first[/yellow]")
        raise typer.Exit(1)
    _print_secrets_report(ensure_secrets(repo))


@secrets_app.command("show")
def secrets_show(
    all_: bool = typer.Option(False, "--all", help="Also print the gateway API key and JWT secret"),
) -> None:
    """Print the admin login (from niyan.yaml, the same source the API uses)."""
    repo = _repo()
    cfg = _load(repo)
    console.print(f"Admin UI user:     {cfg.admin_auth.username}")
    console.print(f"Admin UI password: {cfg.admin_auth.password}")
    if all_:
        console.print(f"Gateway API key:   {cfg.proxy.api_keys[0] if cfg.proxy.api_keys else ''}")
        console.print(f"JWT secret:        {cfg.admin_auth.jwt_secret}")


@gateway_app.command("keys")
def gateway_keys() -> None:
    """List proxy API keys from config."""
    repo = _repo()
    cfg = _load(repo)
    for k in cfg.proxy.api_keys:
        console.print(k)


if __name__ == "__main__":
    app()
