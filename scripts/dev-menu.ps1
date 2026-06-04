# Menú interactivo de desarrollo — API-RAG / Gestor de Responsabilidades
# Uso: .\scripts\dev-menu.ps1
#      .\scripts\dev-menu.ps1 -ApiBase http://localhost:8000

param(
    [string]$ApiBase = "http://localhost:8000"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$SampleMd = Join-Path $Root "sample_documents\demo_policies.md"

function Write-Title([string]$Text) {
    Write-Host ""
    Write-Host "=== $Text ===" -ForegroundColor Cyan
}

function Write-Ok([string]$Text) { Write-Host $Text -ForegroundColor Green }
function Write-Warn([string]$Text) { Write-Host $Text -ForegroundColor Yellow }
function Write-Err([string]$Text) { Write-Host $Text -ForegroundColor Red }

function Read-LineOrDefault([string]$Prompt, [string]$Default) {
    $v = Read-Host $Prompt
    if ([string]::IsNullOrWhiteSpace($v)) { return $Default }
    return $v.Trim()
}

function Invoke-ApiJson {
    param(
        [string]$Method,
        [string]$Path,
        [object]$Body = $null,
        [int]$TimeoutSec = 120
    )
    $uri = "$($ApiBase.TrimEnd('/'))$Path"
    $params = @{
        Method      = $Method
        Uri         = $uri
        ContentType = "application/json; charset=utf-8"
        TimeoutSec  = $TimeoutSec
    }
    if ($null -ne $Body) {
        $params.Body = ($Body | ConvertTo-Json -Compress -Depth 8)
    }
    if ($PSVersionTable.PSVersion.Major -lt 7) {
        $params["UseBasicParsing"] = $true
    }
    return Invoke-RestMethod @params
}

function Wait-HealthReady {
    param([int]$MaxMinutes = 25)
    Write-Title "Esperando /health/ready"
    $deadline = (Get-Date).AddMinutes($MaxMinutes)
    $url = "$($ApiBase.TrimEnd('/'))/health/ready"
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-RestMethod -Uri $url -TimeoutSec 15
            if ($r.healthy -eq $true) {
                Write-Ok "API lista (healthy=true)"
                return $true
            }
            Write-Warn "healthy=false — reintento en 10s..."
        } catch {
            Write-Warn "Sin respuesta ($($_.Exception.Message)) — reintento en 10s..."
        }
        Start-Sleep -Seconds 10
    }
    Write-Err "Timeout. Revisa: docker compose logs api ollama-pull ollama"
    return $false
}

function Get-ComposeFileArgs {
    param(
        [switch]$Prod,
        [switch]$Gpu
    )
    $files = @("-f", "docker-compose.yml")
    if ($Prod) {
        $files += @("-f", "docker-compose.prod.yml")
    }
    if ($Gpu) {
        $files += @("-f", "docker-compose.gpu.yml")
    }
    return $files
}

function Start-DockerStack {
    param(
        [switch]$Prod,
        [switch]$Gpu,
        [switch]$NoBuild,
        [string]$ChatModel = ""
    )
    Set-Location $Root
    $composeArgs = @("compose") + (Get-ComposeFileArgs -Prod:$Prod -Gpu:$Gpu)
    if ($Prod) {
        Write-Warn "Modo producción: solo puerto 8000 al host."
    }
    if ($Gpu) {
        Write-Warn "Modo GPU: Ollama con reserva NVIDIA (requiere nvidia-smi en host/WSL)."
    }
    if ($NoBuild) { $composeArgs += @("up", "-d") }
    else { $composeArgs += @("up", "--build", "-d") }
    if ($ChatModel) {
        $env:OLLAMA_CHAT_MODEL = $ChatModel
        Write-Warn "OLLAMA_CHAT_MODEL=$ChatModel"
    }
    & docker @composeArgs
    if ($LASTEXITCODE -ne 0) { return }
    Wait-HealthReady | Out-Null
    Write-Ok "Swagger: $($ApiBase.TrimEnd('/'))/docs"
}

function Stop-DockerStack {
    param([switch]$Gpu)
    Set-Location $Root
    $composeArgs = @("compose") + (Get-ComposeFileArgs -Gpu:$Gpu) + @("down")
    & docker @composeArgs
}

function Test-OllamaGpu {
    Write-Title "Verificación GPU Ollama"
    & (Join-Path $PSScriptRoot "verify_ollama_gpu.ps1")
}

function Show-DockerLogs {
    $svc = Read-LineOrDefault "Servicio (api | ollama | ollama-pull | mysql | qdrant) [api]" "api"
    Set-Location $Root
    docker compose logs -f --tail 80 $svc
}

function Pull-OllamaModels {
    Set-Location $Root
    Write-Title "Descargando modelos en contenedor ollama"
    docker compose exec -T ollama ollama pull nomic-embed-text
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Fallo pull (¿stack levantado? Usa menú opción 1)."
        return
    }
    $chat = Read-LineOrDefault "Modelo chat [llama3.1:8b] (usa llama3.2:3b si poca RAM)" "llama3.1:8b"
    docker compose exec -T ollama ollama pull $chat
    if ($LASTEXITCODE -eq 0) { Write-Ok "Modelos descargados." }
    else { Write-Err "Fallo al descargar $chat" }
}

function Test-Health {
    Write-Title "Salud de la API"
    try {
        $ping = Invoke-ApiJson -Method GET -Path "/health" -TimeoutSec 15
        Write-Host ($ping | ConvertTo-Json -Depth 4)
        $ready = Invoke-ApiJson -Method GET -Path "/health/ready" -TimeoutSec 30
        Write-Host ($ready | ConvertTo-Json -Depth 6)
        if ($ready.healthy) { Write-Ok "Estado: healthy" }
        else { Write-Warn "Estado: NO healthy — revisa checks en la salida anterior" }
    } catch {
        Write-Err $_.Exception.Message
    }
}

function Invoke-SmokeTest {
    Write-Title "Prueba de humo (Python)"
    $env:API_BASE_URL = $ApiBase.TrimEnd('/')
    & python (Join-Path $PSScriptRoot "smoke_test.py")
    if ($LASTEXITCODE -eq 0) { Write-Ok "Humo OK" } else { Write-Err "Humo falló (código $LASTEXITCODE)" }
}

function Invoke-IngestDemo {
    if (-not (Test-Path $SampleMd)) {
        Write-Err "No existe: $SampleMd"
        return
    }
    $col = Read-LineOrDefault "collection_id" "demo_local"
    Write-Title "Ingesta demo: demo_policies.md"
    $uri = "$($ApiBase.TrimEnd('/'))/api/v1/rag/ingest-file"
    $json = curl.exe -s -X POST $uri `
        -F "collection_id=$col" `
        -F "file=@$SampleMd;type=text/markdown"
    if ($LASTEXITCODE -ne 0) { Write-Err "curl falló"; return }
    $obj = $json | ConvertFrom-Json
    Write-Ok "document_id=$($obj.document_id) chunks=$($obj.chunks_indexed)"
}

function Invoke-IngestFile {
    $path = Read-Host "Ruta del archivo (PDF, TXT, MD, imagen)"
    if (-not (Test-Path $path)) { Write-Err "No existe: $path"; return }
    $col = Read-LineOrDefault "collection_id" "demo_local"
    $docId = Read-LineOrDefault "document_id (vacío = automático)" ""
    Write-Title "Ingesta archivo"
    $uri = "$($ApiBase.TrimEnd('/'))/api/v1/rag/ingest-file"
    $curlArgs = @("-s", "-X", "POST", $uri, "-F", "collection_id=$col", "-F", "file=@$path")
    if ($docId) { $curlArgs += @("-F", "document_id=$docId") }
    $json = curl.exe @curlArgs
    if ($LASTEXITCODE -ne 0) { Write-Err "curl falló"; return }
    $obj = $json | ConvertFrom-Json
    Write-Ok "chunks_indexados=$($obj.chunks_indexed)"
    Write-Host ($obj | ConvertTo-Json)
}

function Invoke-IngestBulk {
    $col = Read-LineOrDefault "collection_id" "demo_local"
    $raw = Read-Host "Rutas separadas por coma"
    $paths = $raw -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    if (-not $paths) { Write-Err "Sin rutas"; return }
    foreach ($p in $paths) {
        if (-not (Test-Path $p)) { Write-Err "No existe: $p"; return }
    }
    $prefix = Read-LineOrDefault "document_id_prefix (opcional)" ""
    Write-Title "Ingesta masiva ($($paths.Count) archivos)"
    $uri = "$($ApiBase.TrimEnd('/'))/api/v1/rag/ingest-files"
    $curlArgs = @("-s", "-X", "POST", $uri, "-F", "collection_id=$col", "-F", "continuar_si_error=true")
    if ($prefix) { $curlArgs += @("-F", "document_id_prefix=$prefix") }
    foreach ($p in $paths) { $curlArgs += @("-F", "files=@$p") }
    $json = curl.exe @curlArgs
    if ($LASTEXITCODE -ne 0) { Write-Err "curl falló"; return }
    $obj = $json | ConvertFrom-Json
    Write-Ok "exitosos=$($obj.exitosos)/$($obj.total_archivos) chunks_totales=$($obj.chunks_totales)"
    foreach ($r in $obj.resultados) {
        $color = if ($r.exito) { "Green" } else { "Red" }
        $msg = if ($r.exito) { "chunks=$($r.chunks_indexados) $($r.metodo_extraccion)" } else { $r.error }
        Write-Host "  $($r.nombre_archivo) [$($r.document_id)] -> $msg" -ForegroundColor $color
    }
}

function Invoke-RagAsk {
    $col = Read-LineOrDefault "collection_id" "demo_local"
    $q = Read-LineOrDefault "Pregunta" "Cual es el SLA de primera respuesta para un incidente P1?"
    $topK = [int](Read-LineOrDefault "top_k" "5")
    Write-Title "RAG ask"
    try {
        $body = @{
            collection_ids = @($col)
            user_message   = $q
            top_k          = $topK
        }
        $ans = Invoke-ApiJson -Method POST -Path "/api/v1/rag/ask" -Body $body -TimeoutSec 600
        Write-Host "confidence: $($ans.confidence)"
        Write-Host "used_chunks: $($ans.used_chunks -join ', ')"
        Write-Host ""
        Write-Host $ans.answer
    } catch {
        Write-Err $_.Exception.Message
    }
}

function Invoke-RagSearch {
    $col = Read-LineOrDefault "collection_id" "demo_local"
    $q = Read-Host "Consulta de búsqueda"
    $topK = [int](Read-LineOrDefault "top_k" "5")
    Write-Title "RAG search"
    try {
        $body = @{
            collection_ids = @($col)
            query          = $q
            top_k          = $topK
        }
        $res = Invoke-ApiJson -Method POST -Path "/api/v1/rag/search" -Body $body
        foreach ($c in $res.chunks) {
            Write-Host "--- score=$($c.score) doc=$($c.document_id) ---" -ForegroundColor DarkGray
            $t = $c.text
            if ($t.Length -gt 400) { $t = $t.Substring(0, 400) + "..." }
            Write-Host $t
        }
    } catch {
        Write-Err $_.Exception.Message
    }
}

function Invoke-ExtractOne {
    $path = Read-Host "Ruta del archivo"
    if (-not (Test-Path $path)) { Write-Err "No existe: $path"; return }
    Write-Title "Extracción (un archivo)"
    $uri = "$($ApiBase.TrimEnd('/'))/api/v1/documents/extract"
    $json = curl.exe -s -X POST $uri -F "file=@$path"
    if ($LASTEXITCODE -ne 0) { Write-Err "curl falló"; return }
    $obj = $json | ConvertFrom-Json
    Write-Ok "metodo=$($obj.metodo_extraccion) paginas=$($obj.paginas) caracteres=$($obj.caracteres)"
    $preview = $obj.texto
    if ($preview.Length -gt 800) { $preview = $preview.Substring(0, 800) + "..." }
    Write-Host "`n--- Vista previa ---`n$preview"
}

function Invoke-ExtractBulk {
    $raw = Read-Host "Rutas separadas por coma"
    $paths = $raw -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    $incluir = Read-LineOrDefault "incluir_texto en respuesta (s/n)" "n"
    $flag = if ($incluir -match '^[sSyY]') { "true" } else { "false" }
    Write-Title "Extracción masiva"
    $uri = "$($ApiBase.TrimEnd('/'))/api/v1/documents/extract-files"
    $curlArgs = @("-s", "-X", "POST", $uri, "-F", "incluir_texto=$flag", "-F", "continuar_si_error=true")
    foreach ($p in $paths) {
        if (-not (Test-Path $p)) { Write-Err "No existe: $p"; return }
        $curlArgs += @("-F", "files=@$p")
    }
    $json = curl.exe @curlArgs
    if ($LASTEXITCODE -ne 0) { Write-Err "curl falló"; return }
    $obj = $json | ConvertFrom-Json
    Write-Ok "exitosos=$($obj.exitosos)/$($obj.total_archivos)"
    foreach ($r in $obj.resultados) {
        $c = if ($r.exito) { "Green" } else { "Red" }
        Write-Host "  $($r.nombre_archivo): $($r.metodo_extraccion) chars=$($r.caracteres)" -ForegroundColor $c
    }
}

function Invoke-AnalyzeDocument {
    param([bool]$UseStream)
    $path = Read-Host "Ruta del plan (PDF/imagen/TXT)"
    if (-not (Test-Path $path)) { Write-Err "No existe: $path"; return }
    $col = Read-LineOrDefault "collection_id del plan" "plan_demo"
    $normas = Read-LineOrDefault "normativa_collection_ids (coma, opcional)" ""
    $prof = Read-LineOrDefault "profundidad (basico|estandar|profundo)" "estandar"
    $nivel = Read-LineOrDefault "nivel territorial" "municipal"
    $guardar = Read-LineOrDefault "guardar_mysql (s/n)" "s"
    $guardarFlag = if ($guardar -match '^[sSyY]') { "true" } else { "false" }

    $uri = "$($ApiBase.TrimEnd('/'))/api/v1/analysis/analyze-document"
    $curlArgs = @(
        "-s", "-X", "POST", $uri,
        "-F", "file=@$path",
        "-F", "collection_id=$col",
        "-F", "profundidad=$prof",
        "-F", "nivel=$nivel",
        "-F", "guardar_mysql=$guardarFlag",
        "-F", "stream=$($UseStream.ToString().ToLower())"
    )
    if ($normas) { $curlArgs += @("-F", "normativa_collection_ids=$normas") }

    Write-Title "Análisis de documento (stream=$UseStream)"
    if ($UseStream) {
        curl.exe -N @curlArgs
    } else {
        $json = curl.exe @curlArgs
        if ($LASTEXITCODE -ne 0) { Write-Err "curl falló"; return }
        $obj = $json | ConvertFrom-Json
        Write-Ok "plan_id=$($obj.plan_id) resp=$($obj.responsabilidades.Count) leyes=$($obj.leyes.Count) matriz=$($obj.matriz.Count)"
        Write-Host ($obj | ConvertTo-Json -Depth 4)
    }
}

function Open-Swagger {
    $url = "$($ApiBase.TrimEnd('/'))/docs"
    Write-Ok "Abriendo $url"
    Start-Process $url
}

function Show-Menu {
    Clear-Host
    Write-Host @"

  API-RAG — Menú de desarrollo
  API: $ApiBase

  [ Docker ]
    1  Levantar stack CPU (build + esperar healthy)
   21  Levantar stack con GPU NVIDIA (build + healthy)
   22  Verificar GPU en Ollama (nvidia-smi + inferencia)
    2  Levantar stack sin rebuild
    3  Levantar modo producción (solo :8000)
    4  Detener stack (compose down)
    5  Ver logs de un servicio
    6  Descargar modelos Ollama (manual)

  [ Salud y pruebas ]
    7  GET /health y /health/ready
    8  Prueba de humo automatizada

  [ RAG ]
    9  Ingesta demo (sample_documents/demo_policies.md)
   10  Ingesta un archivo
   11  Ingesta masiva (varios archivos)
   12  Pregunta con RAG (ask)
   13  Búsqueda vectorial (search)

  [ Documentos / OCR ]
   14  Extraer texto (un archivo)
   15  Extraer texto masivo

  [ Análisis multi-agente ]
   17  Analizar documento (JSON)
   18  Analizar documento (SSE en vivo)

  [ Otros ]
   16  Abrir Swagger en el navegador
    0  Salir

"@ -ForegroundColor White
}

# --- bucle principal ---
Set-Location $Root
while ($true) {
    Show-Menu
    $op = Read-Host "Opción"
    switch ($op) {
        "1" { Start-DockerStack }
        "21" { Start-DockerStack -Gpu }
        "22" { Test-OllamaGpu }
        "2" { Start-DockerStack -NoBuild }
        "3" {
            $m = Read-LineOrDefault "Modelo chat (vacío=default)" ""
            if ($m) { Start-DockerStack -Prod -ChatModel $m }
            else { Start-DockerStack -Prod }
        }
        "4" { Stop-DockerStack }
        "5" { Show-DockerLogs }
        "6" { Pull-OllamaModels }
        "7" { Test-Health }
        "8" { Invoke-SmokeTest }
        "9" { Invoke-IngestDemo }
        "10" { Invoke-IngestFile }
        "11" { Invoke-IngestBulk }
        "12" { Invoke-RagAsk }
        "13" { Invoke-RagSearch }
        "14" { Invoke-ExtractOne }
        "15" { Invoke-ExtractBulk }
        "16" { Open-Swagger }
        "17" { Invoke-AnalyzeDocument -UseStream $false }
        "18" { Invoke-AnalyzeDocument -UseStream $true }
        "0" { Write-Ok "Hasta luego."; break }
        default { Write-Warn "Opción no válida." }
    }
    if ($op -ne "0") {
        Read-Host "`nEnter para continuar"
    }
}
