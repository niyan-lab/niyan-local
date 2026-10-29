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
if ($LASTEXITCODE -ne 0) { throw "python -m venv failed (exit $LASTEXITCODE)" }

$pip = Join-Path $Root ".venv\Scripts\pip.exe"
$niyan = Join-Path $Root ".venv\Scripts\niyan.exe"
if (-not (Test-Path $pip)) {
    throw "venv pip missing at $pip"
}

# Upgrade pip via python -m pip (pip.exe cannot replace itself on Windows).
$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
& $venvPy -m pip install -U pip setuptools wheel --quiet
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed (exit $LASTEXITCODE)" }
& $venvPy -m pip install -e "$Root\cli" --quiet
if ($LASTEXITCODE -ne 0) { throw "pip install of the Niyan CLI failed (exit $LASTEXITCODE)" }

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

# Restrict secret files to the current user BEFORE secrets are written.
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name  # DOMAIN\user
foreach ($f in @($envDest, $yamlDest)) {
    if (Test-Path $f) {
        icacls $f /inheritance:r /grant:r "${identity}:(R,W)" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "icacls failed on $f (exit $LASTEXITCODE)" }
    }
}

$env:NIYAN_ROOT = $Root
$secretsJson = & $niyan secrets init --json
$secretsRc = $LASTEXITCODE
$newAdminPw = $false
try { $report = ($secretsJson | Select-Object -Last 1) | ConvertFrom-Json } catch { $report = $null }
if ($secretsRc -ne 0 -or -not $report -or -not $report.ok) {
    $why = if ($report -and $report.error) { $report.error } else { "exit $secretsRc" }
    throw "niyan secrets init failed; secrets were not changed: $why"
}
foreach ($k in @("rotated", "generated", "kept")) {
    if ($report.$k) { Write-Host ("  {0}: {1}" -f $k, ($report.$k -join ", ")) }
}
foreach ($w in $report.warnings) { Write-Warning $w }
if ($report.generated -contains "admin_auth.password") { $newAdminPw = $true }

$py = Join-Path $Root ".venv\Scripts\python.exe"
& $py -c @"
from pathlib import Path
from niyan.config import load_config
from niyan.litellm_gen import generate_litellm_config
root = Path(r'$Root')
generate_litellm_config(load_config(root / 'niyan.yaml'), root)
print('LiteLLM config generated')
"@
if ($LASTEXITCODE -ne 0) { throw "LiteLLM config generation failed (exit $LASTEXITCODE)" }

$env:NIYAN_ROOT = $Root
& $niyan shell init --shell powershell
if ($LASTEXITCODE -ne 0) { Write-Warning "could not update the PowerShell profile (exit $LASTEXITCODE)" }

Write-Host ""
Write-Host "Installed."
Write-Host ""
Write-Host "  Open a new PowerShell (or reload your profile), then:"
Write-Host ""
Write-Host "    niyan doctor"
Write-Host "    niyan up --build    # first start, and after every git pull / branch switch"
Write-Host "    niyan model pull"
Write-Host "    niyan embeddings pull"
Write-Host ""
if ($newAdminPw) {
    Write-Host "  Admin UI login (new password; stored in niyan.yaml, owner-only ACL). It is now in"
    Write-Host "  your console scrollback - clear it on shared screens. Reprint with: niyan secrets show"
    & $niyan secrets show
} else {
    Write-Host "  Existing secrets kept. Admin UI login: niyan secrets show"
}
Write-Host ""
Write-Host "  Uninstall:            .\uninstall.ps1"
Write-Host "  Repo-local fallback:  .\niyan.cmd <command>"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1) Install & start Ollama for Windows (https://ollama.com)"
Write-Host "  2) Ensure Docker Desktop is running (Linux containers)"
Write-Host "  3) Open a new PowerShell, then: niyan doctor"
Write-Host "  4) niyan up --build   # first start, and after every git pull / branch switch"
Write-Host "  5) See README.md"
