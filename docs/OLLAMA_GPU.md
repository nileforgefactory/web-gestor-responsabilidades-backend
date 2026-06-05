# Ollama con GPU (NVIDIA)

Perfil opcional para acelerar chat, embeddings y validación del scraper cuando hay GPU NVIDIA disponible.

## Requisitos

| Plataforma | Qué instalar |
|------------|----------------|
| **Windows** | Driver NVIDIA + Docker Desktop (WSL2). En WSL: `nvidia-smi` debe funcionar. |
| **Linux** | [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) |

Sin GPU o sin drivers, **no uses** `docker-compose.gpu.yml`; el stack por defecto corre en CPU.

## Arranque con GPU

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

Menú de desarrollo: opción **21** (`.\scripts\dev-menu.ps1`).

Producción + GPU (solo API en :8000):

```powershell
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.gpu.yml up -d --build
```

## Verificar

```powershell
.\scripts\verify_ollama_gpu.ps1
```

O manualmente:

```powershell
docker exec gestor-backend-ollama nvidia-smi
docker exec gestor-backend-ollama ollama run llama3.2:3b "hola" --verbose
```

Durante la inferencia, `nvidia-smi` debe mostrar uso de VRAM y proceso `ollama`.

## Variables opcionales (`.env` o compose)

| Variable | Default (perfil GPU) | Descripción |
|----------|----------------------|-------------|
| `OLLAMA_NUM_PARALLEL` | `2` | Peticiones simultáneas a Ollama |
| `OLLAMA_MAX_LOADED_MODELS` | `1` | Modelos cargados a la vez (VRAM) |

Con GPU, puedes subir concurrencia del scraper con cuidado:

```env
SCRAPER_MAX_CONCURRENCY=2
```

## VRAM orientativa

| Modelo | VRAM ~ (cuantizado) |
|--------|---------------------|
| `nomic-embed-text` | 0.3 GB |
| `llama3.2:3b` | 2 GB |
| `llama3.1:8b` | 5–6 GB |

## Problemas frecuentes

| Síntoma | Solución |
|---------|----------|
| `could not select device driver` al `up` | GPU/drivers no listos; usa compose sin `.gpu.yml` |
| `nvidia-smi` falla dentro del contenedor | Reinstalar driver; reiniciar Docker Desktop / WSL |
| Inferencia igual de lenta | Revisar logs: sin `offload` a GPU; modelo muy grande para VRAM |
| Error al combinar prod + gpu | Usar los tres `-f` en el orden indicado arriba |

La API **no cambia**: sigue usando `OLLAMA_BASE_URL=http://ollama:11434`.
