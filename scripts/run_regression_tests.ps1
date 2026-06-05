# Executa testes regressivos do bot (requer dependências Python instaladas)
# Uso: .\scripts\run_regression_tests.ps1

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "=== Testes regressivos — Pizzaria do Negao ===" -ForegroundColor Cyan

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Python nao encontrado. Instale Python 3.10+ ou use Docker:" -ForegroundColor Yellow
    Write-Host "  docker compose run --rm web python scripts/run_regression_tests.py"
    exit 1
}

$venv = ".venv"
if (-not (Test-Path $venv)) {
    Write-Host "Criando venv..." -ForegroundColor Gray
    python -m venv $venv
}

& "$venv\Scripts\pip.exe" install -q -r requirements.txt
& "$venv\Scripts\python.exe" scripts/run_regression_tests.py
exit $LASTEXITCODE
