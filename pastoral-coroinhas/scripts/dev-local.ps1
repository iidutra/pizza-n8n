#Requires -Version 5.1
param(
    [switch]$CriarCoordenador,
    [switch]$SeedDemo,
    [string]$Email,
    [string]$Senha
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Backend = Join-Path $Root "backend"
$Venv = Join-Path $Backend ".venv"

Write-Host "Pastoral Coroinhas - setup local (sem Docker)" -ForegroundColor Cyan

if (-not (Test-Path (Join-Path $Root ".env"))) {
    Copy-Item (Join-Path $Root ".env.local.example") (Join-Path $Root ".env")
    Write-Host "Criado .env a partir de .env.local.example"
}

if (-not (Test-Path $Venv)) {
    Write-Host "Criando venv em backend\.venv ..."
    python -m venv $Venv
}

$Python = Join-Path $Venv "Scripts\python.exe"
$Pip = Join-Path $Venv "Scripts\pip.exe"

& $Pip install -r (Join-Path $Backend "requirements.txt") -q 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Falha ao instalar dependências Python. Rode manualmente: backend\.venv\Scripts\pip install -r backend\requirements.txt"
}

Push-Location $Backend
& $Python manage.py migrate
& $Python manage.py setup_missas 2>$null
if ($SeedDemo) {
    & $Python manage.py seed_demo
}

if ($CriarCoordenador) {
    if (-not $Email -or -not $Senha) {
        Write-Error "Use -Email e -Senha com -CriarCoordenador"
    }
    & $Python manage.py criar_coordenador --email $Email --senha $Senha --nome Coordenador
    Pop-Location
    exit 0
}

Write-Host ""
Write-Host "API: http://localhost:8000" -ForegroundColor Green
Write-Host "Frontend (outro terminal): cd frontend; npm run dev" -ForegroundColor Yellow
Write-Host "Criar coordenador:" -ForegroundColor Yellow
Write-Host "  .\scripts\dev-local.ps1 -CriarCoordenador -Email coord@paroquia.org -Senha admin123"
Write-Host "Popular dados demo:" -ForegroundColor Yellow
Write-Host "  .\scripts\dev-local.ps1 -SeedDemo"
Write-Host ""

& $Python manage.py runserver
Pop-Location
