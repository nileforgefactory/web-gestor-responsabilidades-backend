# Arranque limpio: borra volúmenes Docker, levanta infra, aplica migraciones manualmente y arranca la API.
# Uso: .\scripts\db-fresh-start.ps1
# Requiere: Docker Desktop, estar en la raíz del repositorio.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot | Out-Null
Set-Location ..

Write-Host "==> Deteniendo contenedores y eliminando volúmenes (MySQL, Qdrant, Redis, Ollama)..." -ForegroundColor Cyan
docker compose down -v --remove-orphans

Write-Host "==> Construyendo imagen API..." -ForegroundColor Cyan
docker compose build api

Write-Host "==> Levantando MySQL (esperando healthy)..." -ForegroundColor Cyan
docker compose up -d mysql
$retries = 40
for ($i = 1; $i -le $retries; $i++) {
    $status = docker inspect --format='{{.State.Health.Status}}' gestor-backend-mysql 2>$null
    if ($status -eq "healthy") { break }
    if ($i -eq $retries) { throw "MySQL no llegó a healthy a tiempo." }
    Start-Sleep -Seconds 3
}

Write-Host "==> Aplicando migraciones Alembic (manual)..." -ForegroundColor Cyan
docker compose run --rm api alembic upgrade head
docker compose run --rm api alembic current

Write-Host "==> Levantando el resto de servicios..." -ForegroundColor Cyan
docker compose up -d

Write-Host ""
Write-Host "Listo. Verifique:" -ForegroundColor Green
Write-Host "  curl http://localhost:8000/health/ready"
Write-Host "  Login: superadmin@gestor.local / SuperAdmin123! (o AUTH_BOOTSTRAP_* en .env)"
Write-Host "  Docs:  http://localhost:8000/docs"
