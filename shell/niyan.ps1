# Niyan PowerShell hook — sourced after NIYAN_ROOT is set (see `niyan shell init`).
# Puts the Windows venv Scripts directory on PATH (like shell/niyan.sh on Unix).

if (-not $env:NIYAN_ROOT) {
    Write-Error "niyan: NIYAN_ROOT is not set; run: niyan shell init"
    return
}

if (-not $env:NIYAN_HOME) {
    $env:NIYAN_HOME = $env:NIYAN_ROOT
}

$niyanBin = Join-Path $env:NIYAN_ROOT ".venv\Scripts"
if (-not (Test-Path $niyanBin)) {
    $niyanBin = Join-Path $env:NIYAN_ROOT ".venv\bin"
}

if (Test-Path $niyanBin) {
    $parts = $env:PATH -split ";"
    if ($parts -notcontains $niyanBin) {
        $env:PATH = "$niyanBin;$env:PATH"
    }
} else {
    Write-Warning "niyan: missing $niyanBin — re-run .\install.ps1"
}
