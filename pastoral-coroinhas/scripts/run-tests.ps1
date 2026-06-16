$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "=== Backend (pytest) ===" -ForegroundColor Cyan
Push-Location "$root\backend"
if (-not (Test-Path ".\.venv")) {
    python -m venv .venv
}
.\.venv\Scripts\pip install -q -r requirements.txt -r requirements-dev.txt 2>&1 | Out-Null
.\.venv\Scripts\pytest @args
$backendExit = $LASTEXITCODE
Pop-Location

Write-Host "`n=== Frontend (vitest) ===" -ForegroundColor Cyan
Push-Location "$root\frontend"
if (-not (Test-Path ".\node_modules")) {
    npm ci 2>&1 | Out-Null
}
npm test
$frontendExit = $LASTEXITCODE
Pop-Location

if ($backendExit -ne 0 -or $frontendExit -ne 0) {
    exit 1
}
