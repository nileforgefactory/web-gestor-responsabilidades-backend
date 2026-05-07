# curl.exe desde PowerShell: el JSON debe ir en comillas SIMPLES.
# Si usas comillas DOBLES y \" PowerShell rompe el cuerpo (error json_invalid).

$Uri = if ($env:RAG_API_URL) { $env:RAG_API_URL } else { "http://localhost:8000/api/v1/rag/ask" }

$payload = @{
    collection_ids = @("demo_local")
    user_message   = "¿Cuál es el SLA de primera respuesta para un incidente P1?"
    top_k          = 5
} | ConvertTo-Json -Compress -Depth 5

$curlExe = Join-Path $env:SystemRoot "System32\curl.exe"
if (-not (Test-Path -LiteralPath $curlExe)) { $curlExe = "curl.exe" }

# --data-binary vía archivo evita todas las trampas de comillas del shell
$dataPath = Join-Path ([System.IO.Path]::GetTempPath()) ("rag-ask-{0}.json" -f [Guid]::NewGuid())
try {
    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($dataPath, $payload, $utf8NoBom)
    Write-Host "[demo-ask-curl] POST $Uri" -ForegroundColor Cyan
    & $curlExe -sS -X POST $Uri `
        -H "Content-Type: application/json; charset=utf-8" `
        --data-binary "@$dataPath"
} finally {
    Remove-Item -LiteralPath $dataPath -Force -ErrorAction SilentlyContinue
}

Write-Host ""
