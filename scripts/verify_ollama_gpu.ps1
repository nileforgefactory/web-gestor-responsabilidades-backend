# Verifica que el contenedor Ollama ve la GPU NVIDIA y puede inferir.
# Uso: .\scripts\verify_ollama_gpu.ps1
#      .\scripts\verify_ollama_gpu.ps1 -ChatModel llama3.2:3b

param(
    [string]$ContainerName = "gestor-backend-ollama",
    [string]$ChatModel = "llama3.2:3b",
    [int]$TimeoutSec = 180
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Ok([string]$Text) { Write-Host "[OK] $Text" -ForegroundColor Green }
function Write-Warn([string]$Text) { Write-Host "[WARN] $Text" -ForegroundColor Yellow }
function Write-Fail([string]$Text) { Write-Host "[FAIL] $Text" -ForegroundColor Red }

Write-Host ""
Write-Host "=== Verificación GPU — Ollama ===" -ForegroundColor Cyan
Write-Host "Contenedor: $ContainerName"
Write-Host "Modelo prueba: $ChatModel"
Write-Host ""

$running = docker inspect -f "{{.State.Running}}" $ContainerName 2>$null
if ($LASTEXITCODE -ne 0 -or $running -ne "true") {
    Write-Fail "El contenedor '$ContainerName' no está en ejecución."
    Write-Host "Levanta el stack con GPU:"
    Write-Host "  docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d"
    Write-Host "O menú dev: opción 21"
    exit 1
}
Write-Ok "Contenedor en ejecución"

Write-Host ""
Write-Host "--- nvidia-smi (dentro del contenedor) ---" -ForegroundColor DarkGray
$smi = docker exec $ContainerName nvidia-smi 2>&1
$smi | ForEach-Object { Write-Host $_ }
if ($LASTEXITCODE -ne 0) {
    Write-Fail "nvidia-smi no disponible en el contenedor."
    Write-Host "Revisa driver NVIDIA, WSL2 y que arrancaste con docker-compose.gpu.yml"
    exit 1
}
Write-Ok "nvidia-smi respondió"

Write-Host ""
Write-Host "--- Inferencia corta (puede tardar 1–2 min la primera vez) ---" -ForegroundColor DarkGray
$prompt = "Responde solo: OK"
$logBefore = (docker logs --tail 5 $ContainerName 2>&1) -join "`n"

docker exec $ContainerName ollama run $ChatModel $prompt --verbose 2>&1 | ForEach-Object {
    Write-Host $_
}
if ($LASTEXITCODE -ne 0) {
    Write-Fail "ollama run falló (¿modelo descargado? docker compose up ollama-pull)"
    exit 1
}
Write-Ok "Inferencia completada"

$logAfter = docker logs --tail 80 $ContainerName 2>&1
$gpuHints = @("GPU", "gpu", "CUDA", "cuda", "offload", "offloaded", "vram", "VRAM")
$found = $false
foreach ($line in ($logAfter -split "`n")) {
    foreach ($h in $gpuHints) {
        if ($line -match $h) {
            Write-Host "  log: $line" -ForegroundColor DarkGreen
            $found = $true
            break
        }
    }
}
if ($found) {
    Write-Ok "Logs sugieren uso de aceleración GPU"
} else {
    Write-Warn "No se encontraron líneas GPU en logs recientes; puede estar en CPU o logs ya rotados."
    Write-Host "  Comprueba VRAM con: docker exec $ContainerName nvidia-smi"
}

Write-Host ""
Write-Ok "Verificación finalizada. Si nvidia-smi muestra proceso ollama bajo carga, la GPU está activa."
