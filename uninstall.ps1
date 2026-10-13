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

$niyan = Join-Path $Root ".venv\Scripts\niyan.exe"
if (Test-Path $niyan) {
    $args = @("uninstall", "--yes")
    if ($Volumes) { $args += "--volumes" }
    if ($KeepConfig) { $args += "--keep-config" }
    & $niyan @args
    exit $LASTEXITCODE
}

Write-Host "CLI venv missing — falling back to Compose + shell cleanup"

if (Get-Command docker -ErrorAction SilentlyContinue) {
    $compose = @("docker", "compose", "--project-name", "niyan", "-f", "$Root\deploy\docker-compose.yml")
    $hostOverlay = Join-Path $Root "deploy\docker-compose.host-ollama.yml"
    if (Test-Path $hostOverlay) {
        $compose += @("-f", $hostOverlay)
    }
    $down = @("down", "--remove-orphans")
    if ($Volumes) { $down += "--volumes" }
    & $compose[0] $compose[1..($compose.Length-1)] @down
}

$env:NIYAN_ROOT = $Root
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
if ($py -and (Test-Path (Join-Path $Root "cli\niyan\shell_init.py"))) {
    $env:PYTHONPATH = Join-Path $Root "cli"
    & $py.Source -c "from pathlib import Path; from niyan.shell_init import init_shell; init_shell(Path(r'$Root'), reverse=True)"
}

$venv = Join-Path $Root ".venv"
if (Test-Path $venv) { Remove-Item -Recurse -Force $venv }

if (-not $KeepConfig) {
    foreach ($name in @("niyan.yaml", ".env")) {
        $p = Join-Path $Root $name
        if (Test-Path $p) { Remove-Item -Force $p }
    }
}

$generated = Join-Path $Root "services\litellm\config.generated.yaml"
if (Test-Path $generated) { Remove-Item -Force $generated }

Write-Host "Uninstalled. Reinstall with .\install.ps1"
