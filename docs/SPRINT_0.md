# Sprint 0 — Infraestructura estable

**Estado:** Implementado  
**Objetivo:** Levantar el stack con un solo flujo reproducible, healthchecks fiables y modelos Ollama alineados al plan de producto.

---

## Alcance entregado

| ID | Tarea | Archivos |
|----|--------|----------|
| 0.1 | Imagen API con dependencias OCR (Tesseract + Poppler) | `Dockerfile` |
| 0.2 | Healthcheck del contenedor `api` | `Dockerfile`, `docker-compose.yml` |
| 0.3 | Orden de arranque y variables centralizadas | `docker-compose.yml`, `.env.example` |
| 0.4 | Perfil producción (solo puerto 8000 público) | `docker-compose.prod.yml` |
| 0.5 | Modelo de chat por defecto `llama3.1:8b` (configurable) | `docker-compose.yml`, `ollama_pull.sh` |
| 0.6 | Menú interactivo de desarrollo | `scripts/dev-menu.ps1` |
| 0.7 | Prueba de humo automatizada | `scripts/smoke_test.py` |

---

## Requisitos

- Docker Desktop con **Compose v2.20+** (soporta `depends_on: service_completed_successfully`).
- ~8 GB RAM libres si usas `llama3.1:8b`; en equipos limitados usa `llama3.2:3b` (ver abajo).
- Primera ejecución: descarga de modelos Ollama (puede tardar 15–40 min según red).

---

## Arranque en desarrollo

### Compose CPU o GPU

```powershell
# CPU
docker compose up --build -d

# GPU NVIDIA
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build -d
```

MySQL vacío; aplicar esquema manualmente con `alembic upgrade head`. Ver [MIGRATIONS.md](MIGRATIONS.md).

### Opción recomendada (PowerShell)

```powershell
.\scripts\dev-menu.ps1
```

Elige **opción 1** (levantar stack). Espera `healthy=true` o usa **opción 7** para comprobar salud. **Opción 16** abre Swagger.

### Máquina con poca RAM (modelo ligero)

En el menú, opción **3** (producción) o **1** tras definir en la sesión:

```powershell
$env:OLLAMA_CHAT_MODEL = "llama3.2:3b"
.\scripts\dev-menu.ps1
```

### Compose manual

```powershell
docker compose up --build -d
```

### Compose con GPU NVIDIA (opcional)

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build -d
.\scripts\verify_ollama_gpu.ps1
```

Ver [OLLAMA_GPU.md](OLLAMA_GPU.md).

Comprobar:

```powershell
Invoke-RestMethod http://localhost:8000/health/ready
```

---

## Arranque en producción (solo API expuesta)

```powershell
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

O con el menú: opción **3** (modo producción).

En este modo **MySQL, Qdrant y Ollama** no publican puertos al host; solo `8000`.

> **Nota:** `docker-compose.prod.yml` usa `ports: !reset []` (Compose 2.24+). Si tu versión no lo soporta, elimina manualmente los bloques `ports` de mysql/ollama/qdrant al desplegar.

---

## Servicios y puertos (desarrollo)

| Servicio | Contenedor | Puerto host | Rol |
|----------|------------|---------------|-----|
| api | api-rag-api | 8000 | FastAPI, único punto de entrada HTTP |
| mysql | api-rag-mysql | 3307 | Planes y conocimiento |
| qdrant | api-rag-qdrant | 6333 | Vectores RAG |
| ollama | api-rag-ollama | 11434 | LLM y embeddings |
| ollama-pull | api-rag-ollama-pull | — | Job único: descarga modelos |

---

## Variables de entorno

Copia `.env.example` a `.env` para personalizar. En Docker las principales están en `docker-compose.yml`:

| Variable | Default | Descripción |
|----------|---------|-------------|
| `OLLAMA_CHAT_MODEL` | `llama3.1:8b` | Modelo de chat |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Embeddings (768 dims) |
| `VECTOR_SIZE` | `768` | Debe coincidir con el modelo de embedding |
| `MYSQL_URL` | (en compose) | Conexión async a MySQL |

---

## Prueba de humo

Con el stack arriba y `healthy=true`:

```powershell
python scripts/smoke_test.py
```

Flujo: `GET /health/ready` → `POST /rag/ingest-text` → `POST /rag/ask` con `used_chunks` no vacío.

Variable opcional:

```powershell
$env:API_BASE_URL = "http://localhost:8000"
python scripts/smoke_test.py
```

---

## Depuración habitual

| Síntoma | Qué revisar |
|---------|-------------|
| API en `starting` mucho tiempo | `docker compose logs ollama-pull` — descarga de modelos |
| `/health/ready` → `healthy: false` (Ollama) | Modelos no registrados; menú **opción 6** o `docker compose build ollama-pull && docker compose up ollama-pull` |
| `503` en ingest/ask | Mismo chequeo Ollama + Qdrant en el JSON de `/health/ready` |
| Contenedor `api` unhealthy | `docker compose logs api` — fallo en `wait_services.py` o uvicorn |
| Cambio de modelo de embedding | `docker compose down -v` (borra volumen Qdrant) y volver a indexar |

---

## Criterios de aceptación

- [ ] `docker compose up --build` termina sin error y `api` queda `healthy`.
- [ ] `GET /health/ready` devuelve HTTP 200 y `"healthy": true`.
- [ ] `python scripts/smoke_test.py` finaliza con código 0.
- [ ] Swagger accesible en `/docs`.

---

## Siguiente paso

Sprint 1 — OCR y endpoint `POST /api/v1/documents/extract`: ver [SPRINT_1.md](./SPRINT_1.md).
