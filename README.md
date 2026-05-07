# Agentic RAG API (FastAPI + vertical slices)

MVP para **demo local**: ingesta de documentos (TXT/MD/PDF), embeddings con **Ollama**, recuperación desde **Qdrant** y respuesta con modelo local mediante `POST /api/v1/rag/ask`.

## Arquitectura (vertical slicing)

Capacidad RAG en `app/slices/rag`:

- `router.py`: endpoints HTTP
- `schemas.py`: contratos
- `service.py`: chunking por caracteres, embeddings, construcción de contexto y chat
- `repository.py`: Qdrant
- `extract.py`: extracción de texto desde archivos subidos
- `ollama_client.py`: llamadas a Ollama sin SDK externo

## Proyecto Docker Compose: API-RAG

El archivo `docker-compose.yml` define **`name: api-rag`** (nombre del proyecto Compose). Los contenedores y volúmenes quedarán etiquetados bajo ese prefijo (visible en Docker Desktop como proyecto **api-rag**).

## Levantar todo con Docker Compose (recomendado)

### 1) Subir infraestructura

```powershell
docker compose up --build
```

**Primera vez:** el servicio `ollama-pull` descarga embeddings + modelo de chat **antes** de arrancar `api` (Swagger no se queda contra un registry vacío). Puede llevar bastante tiempo según tu red y CPU — revisa Docker Desktop hasta ver `ollama-pull` terminado OK.

Compose usa `depends_on.condition: service_completed_successfully`; requiere **Docker Compose plugin v2.20+**.

Servicios útiles una vez la API está arriba:

- **Swagger UI**: [`http://localhost:8000/docs`](http://localhost:8000/docs)
- **`GET /health/ready`** (lista Qdrant, registry Ollama y modelos requeridos) — usar si Swagger devuelve 502/504 o `503`
- **`GET /health`** (ping mínimo)
- Qdrant: `http://localhost:6333` · Ollama: `http://localhost:11434`

### 2) Pull manual (solo si falla `ollama-pull` o tras cortes de red)

```powershell
.\scripts\pull-models.ps1
```

### 3) Comprobar listo antes de probar Swagger

Abre [`http://localhost:8000/health/ready`](http://localhost:8000/health/ready) y confirma `healthy: true`. Si aparece `false`, lee los bloques `checks` (daemon Ollama, modelos esperados vs `installed_models_sample`).

### 4) Ingesta de ejemplo (archivo montado en el contenedor)

El `docker-compose.yml` monta `./sample_documents` en `/samples` (solo lectura). Puedes subir el Markdown de demostración:

```powershell
curl.exe -X POST "http://localhost:8000/api/v1/rag/ingest-file" `
  -F "collection_id=demo_local" `
  -F "file=@sample_documents/demo_policies.md;type=text/markdown"
```

### 5) Pregunta con RAG + LLM local

#### ⚠ Por qué falla `curl.exe` cuando “parece bien” el JSON

Si en **PowerShell** ejecutas algo como:

```powershell
# ❌ MAL — no copies esto: PowerShell reinterpreta `\"` y el JSON llega corrupto → json_invalid / bad range
curl.exe ... -d "{\"collection_ids\":[...]}"
```

PowerShell procesa antes la cadena: las barras `\` escapan comillas dentro de `"..."`, el JSON llega mal a `curl`, y aparece `curl: (3) bad range specification` más `¿CuÃ¡l` (encoding roto).

**Soluciones que sí funcionan (elige una):**

**Opción recomendada — script con `curl` usando archivo temporal (sin trampas de comillas):**

```powershell
.\scripts\demo-ask-curl.ps1
```

**Opción — `Invoke-RestMethod` (sin `curl`):**

```powershell
.\scripts\demo-ask.ps1
```

Pregunta personalizada:

```powershell
.\scripts\demo-ask.ps1 -Question "¿Qué SLA aplica a un P2?"
```

**Opción — `curl` sin pelear con PowerShell** (archivo JSON UTF-8, sin BOM):

```powershell
curl.exe -X POST "http://localhost:8000/api/v1/rag/ask" `
  -H "Content-Type: application/json; charset=utf-8" `
  --data-binary "@scripts/ask-body-demo.json"
```

**Opción — una sola línea con comillas simples externas** (JSON interno con `"` dobles):

```powershell
curl.exe -X POST "http://localhost:8000/api/v1/rag/ask" -H "Content-Type: application/json; charset=utf-8" -d '{"collection_ids":["demo_local"],"user_message":"Cual es el SLA de primera respuesta para un incidente P1?","top_k":5}'
```

Si obtienes `json_invalid` en `body` posición 1, suele ser **JSON mal formado**: comillas tipográficas, `'` alrededor del objeto, **línea de comando pegada** (dos `-H` o mitad de URL mezclada con el JSON), o BOM. La API ahora quita BOM UTF-8 y la respuesta 422 incluye `hint` con orientación.

**Opción — Swagger**: `http://localhost:8000/docs` → **`POST /api/v1/rag/ask`** → *Try it out* → *Execute*.

## Endpoints principales

- `GET /health/ready` — depuracion antes de ejecutar ingest/ask desde Swagger
- `GET /health`
- `POST /api/v1/rag/ingest-text` — ingesta de texto plano (JSON)
- `POST /api/v1/rag/ingest-file` — ingesta multipart (PDF/TXT/MD)
- `POST /api/v1/rag/search` — solo recuperación
- `POST /api/v1/rag/agent-context` — bloque de contexto ensamblado (útil para agentes)
- `POST /api/v1/rag/ask` — respuesta final con citas y `used_chunks`

## Variables de entorno

Ver `.env.example`. En Docker ya vienen prefijadas en `docker-compose.yml`.

## Notas operativas

- **Swagger + timeouts**: `/rag/ask` puede tardar minutos la primera vez (embeddings + generación CPU). Espera respuesta completa antes de repetir llamadas; errores claros incluyen HTTP **504** (timeout hacia Ollama).
- **Sin APIs externas**: todo corre en tu máquina vía contenedores.
- **Dimensión de vectores**: `VECTOR_SIZE` debe coincidir con el modelo de embeddings de Ollama (`nomic-embed-text` → 768). Si cambiaste modelos o probaste un MVP antiguo, borra el volumen de Qdrant para recrear colección (`docker compose down -v`).
- El contenedor **`api`** espera `qdrant` + `ollama` sanos y el job **`ollama-pull`** terminado antes de lanzar uvicorn (`scripts/wait_services.py` vuelve a comprobar el registry dentro del mismo entrypoint).
- Si **Qdrant** queda `unhealthy`, comprueba si la imagen carece de `wget` y ajusta el `healthcheck` del servicio según tus logs Docker.
- Opcional rápido para desarrollo: `USE_OLLAMA=false` + `VECTOR_SIZE=128` usa embeddings sintéticos; **no** sirve como demo semántica real.

## Si aparece `set: illegal option -` en `ollama_pull.sh`

Cuando ese script se montaba desde Windows (`CRLF`), el `\r` rompía `set -eu`.

**Ya no se monta así**: el servicio **`ollama-pull`** se construye con `Dockerfile.ollama-pull` y aplica `sed` para eliminar `\r` antes de ejecutar.

Si modificas `scripts/ollama_pull.sh` localmente, vuelve a construir ese servicio:

```powershell
docker compose build ollama-pull --no-cache
docker compose up
```
