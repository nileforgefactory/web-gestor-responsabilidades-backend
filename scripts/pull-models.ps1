$ErrorActionPreference = "Stop"

# Proyecto Compose: api-rag (ver `name` en docker-compose.yml)
Write-Host "Descargando modelos en el contenedor ollama (requiere compose en ejecución)..." 
docker compose exec ollama ollama pull nomic-embed-text
docker compose exec ollama ollama pull llama3.2:3b
Write-Host "Listo."
