Param(
    [string]$Uri = "http://localhost:8000/api/v1/rag/ask",
    [string]$CollectionId = "demo_local",
    [string]$Question = "¿Cuál es el SLA de primera respuesta para un incidente P1?",
    [ValidateRange(1, 25)][int]$TopK = 5
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$bodyHashtable = [ordered]@{
    collection_ids = @($CollectionId)
    user_message   = $Question
    top_k          = $TopK
}
$body = ($bodyHashtable | ConvertTo-Json -Compress -Depth 5)

$params = @{
    Method      = "Post"
    Uri         = $Uri
    ContentType = "application/json; charset=utf-8"
    Body        = $body
}

if ($PSVersionTable.PSVersion.Major -lt 7) {
    $params["UseBasicParsing"] = $true
}

Invoke-RestMethod @params
