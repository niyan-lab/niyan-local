# Remove a from-source Niyan install (Compose stack, shell hook, venv).
# Does not delete this checkout.
# Usage: powershell -ExecutionPolicy Bypass -File .\uninstall.ps1 [-Volumes] [-KeepConfig] [-Yes]

param(
    [switch]$Volumes,
    [switch]$KeepConfig,
    [switch]$Yes
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

Write-Host "==> Niyan uninstall (Windows)"
Write-Host "Repo: $Root"

if (-not $Yes) {
    $msg = "Stop Compose, unwire PowerShell, and delete .venv"
    if ($Volumes) { $msg += " (including Docker volumes)" }
    $reply = Read-Host "$msg. Continue? [y/N]"
    if ($reply -notmatch '^(y|yes)$') {
        Write-Host "Aborted."
        exit 1
    }
}

$venv = Join-Path $Root ".venv"
$niyan = Join-Path $Root ".venv\Scripts\niyan.exe"
if ((Test-Path $niyan) -and ($env:NIYAN_UNINSTALL_SKIP_CLI -ne "1")) {
    $cliArgs = @("uninstall", "--yes")
    if ($Volumes) { $cliArgs += "--volumes" }
    if ($KeepConfig) { $cliArgs += "--keep-config" }
    & $niyan @cliArgs
    if ($LASTEXITCODE -eq 0) {
        # The CLI cannot delete its own locked venv on Windows; do it now that it exited.
        if (Test-Path $venv) { Remove-Item -Recurse -Force $venv }
        exit 0
    }
    if ($LASTEXITCODE -eq 3) {
        # Compose could not stop the stack; the CLI removed nothing. Do not fall back.
        exit 3
    }
    Write-Warning "CLI failed (exit $LASTEXITCODE) - falling back to manual cleanup"
} else {
    Write-Host "CLI venv missing (or skipped) - falling back to Compose + shell cleanup"
}

$fallbackRc = 0
if (Get-Command docker -ErrorAction SilentlyContinue) {
    # Same order as cli/niyan/project.py: env, .env key, legacy `niyan` for an old .env, default.
    $project = $env:NIYAN_COMPOSE_PROJECT
    $envFileP = Join-Path $Root ".env"
    if (-not $project -and (Test-Path $envFileP)) {
        $m = Select-String -Path $envFileP -Pattern '^NIYAN_COMPOSE_PROJECT=(.+)$' | Select-Object -Last 1
        if ($m) { $project = $m.Matches[0].Groups[1].Value.Trim().Trim('"', "'") } else { $project = "niyan" }
    }
    if (-not $project) { $project = "niyan" }
    $composeArgs = @("compose", "--project-name", $project, "-f", "$Root\deploy\docker-compose.yml")
    $hostOverlay = Join-Path $Root "deploy\docker-compose.host-ollama.yml"
    if (Test-Path $hostOverlay) { $composeArgs += @("-f", $hostOverlay) }
    $envFile = Join-Path $Root ".env"
    $envText = ""
    if (Test-Path $envFile) {
        $composeArgs += @("--env-file", $envFile)
        $envText = Get-Content -Raw $envFile
    }
    foreach ($p in @("ollama", "obs", "guard-llm", "guard-nemo", "admin", "vector-qdrant", "vector-pg")) {
        $composeArgs += @("--profile", $p)
    }
    # `down` still interpolates ${VAR:?} guards; dummy values for missing ones (nothing starts).
    foreach ($v in @("POSTGRES_PASSWORD", "LANGFUSE_NEXTAUTH_SECRET", "LANGFUSE_SALT", "LANGFUSE_ENCRYPTION_KEY",
                     "LITELLM_MASTER_KEY", "NIYAN_ADMIN_PASSWORD", "NIYAN_JWT_SECRET")) {
        if (-not [Environment]::GetEnvironmentVariable($v) -and ($envText -notmatch "(?m)^$v=.+")) {
            Set-Item -Path "env:$v" -Value "__niyan_unused__"
        }
    }
    $env:NIYAN_ROOT = $Root
    $down = @("down", "--remove-orphans")
    if ($Volumes) { $down += "--volumes" }
    & docker @composeArgs @down
    if ($LASTEXITCODE -ne 0) {
        Write-Error "docker compose down failed (is Docker running?). Nothing was removed. Start Docker and re-run .\uninstall.ps1." -ErrorAction Continue
        exit 3
    }
} else {
    Write-Warning "docker not found - skipping container/volume cleanup"
}

$env:NIYAN_ROOT = $Root
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
if ($py -and (Test-Path (Join-Path $Root "cli\niyan\shell_init.py"))) {
    $env:PYTHONPATH = Join-Path $Root "cli"
    & $py.Source -c "from pathlib import Path; from niyan.shell_init import init_shell; init_shell(Path(r'$Root'), reverse=True)"
}

if (Test-Path $venv) { Remove-Item -Recurse -Force $venv }

if (-not $KeepConfig) {
    foreach ($name in @("niyan.yaml", ".env")) {
        $p = Join-Path $Root $name
        if (Test-Path $p) { Remove-Item -Force $p }
    }
}

$generated = Join-Path $Root "services\litellm\config.generated.yaml"
if (Test-Path $generated) { Remove-Item -Force $generated }

if ($fallbackRc -ne 0) {
    Write-Host "Uninstall finished WITH ERRORS (see above)."
    exit $fallbackRc
}
Write-Host "Uninstalled. Reinstall with .\install.ps1"
