# Niyan bootstrap for Windows (Docker Desktop + host Ollama).
# Requires: Python 3.9+, Docker Desktop, Ollama (https://ollama.com)
# Usage:  powershell -ExecutionPolicy Bypass -File .\install.ps1

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

Write-Host "==> Niyan installer (Windows)"
Write-Host "Repo: $Root"

function Assert-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is required on PATH"
    }
}

$python = $null
foreach ($candidate in @("python", "py")) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $python = $candidate
        break
    }
}
if (-not $python) {
    throw "Python 3.9+ is required (python or py on PATH)"
}

Assert-Command "docker"

Write-Host "Creating venv …"
& $python -m venv "$Root\.venv"

$pip = Join-Path $Root ".venv\Scripts\pip.exe"
$niyan = Join-Path $Root ".venv\Scripts\niyan.exe"
if (-not (Test-Path $pip)) {
    throw "venv pip missing at $pip"
}

& $pip install -U pip setuptools wheel --quiet
& $pip install -e "$Root\cli" --quiet

$envExample = Join-Path $Root ".env.example"
$envDest = Join-Path $Root ".env"
if ((Test-Path $envExample) -and -not (Test-Path $envDest)) {
    Copy-Item $envExample $envDest
}

$yamlExample = Join-Path $Root "configs\niyan.example.yaml"
$yamlDest = Join-Path $Root "niyan.yaml"
if ((Test-Path $yamlExample) -and -not (Test-Path $yamlDest)) {
    Copy-Item $yamlExample $yamlDest
}

$env:NIYAN_ROOT = $Root
& $niyan secrets init
if ($LASTEXITCODE -ne 0) { throw "niyan secrets init failed" }
# Restrict secret files to the current user
foreach ($f in @($envDest, $yamlDest)) {
    if (Test-Path $f) { icacls $f /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null }
}

$py = Join-Path $Root ".venv\Scripts\python.exe"
& $py -c @"
from pathlib import Path
from niyan.config import load_config
from niyan.litellm_gen import generate_litellm_config
root = Path(r'$Root')
generate_litellm_config(load_config(root / 'niyan.yaml'), root)
print('LiteLLM config generated')
"@

$env:NIYAN_ROOT = $Root
& $niyan shell init --shell powershell

Write-Host ""
Write-Host "Installed."
Write-Host ""
Write-Host "  Open a new PowerShell (or reload your profile), then:"
Write-Host ""
Write-Host "    niyan doctor"
Write-Host "    niyan up"
Write-Host "    niyan model pull"
Write-Host "    niyan embeddings pull"
Write-Host ""
Write-Host "  Admin UI login: run  niyan secrets show"
Write-Host ""
Write-Host "  Uninstall:            .\uninstall.ps1"
Write-Host "  Repo-local fallback:  .\niyan.cmd <command>"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1) Install & start Ollama for Windows (https://ollama.com)"
Write-Host "  2) Ensure Docker Desktop is running (Linux containers)"
Write-Host "  3) Open a new PowerShell, then: niyan doctor"
Write-Host "  4) niyan up"
Write-Host "  5) See README.md"
