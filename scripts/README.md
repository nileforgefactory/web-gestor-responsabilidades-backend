# Scripts del proyecto

Punto de entrada recomendado: menú interactivo. Documentación general del API: [README.md](../README.md).

## Menú interactivo (recomendado)

```powershell
.\scripts\dev-menu.ps1
```

| Opciones | Área |
|----------|------|
| 1–6 | Docker (stack, prod, logs, modelos) |
| 7–8 | Salud y humo |
| 9–13 | RAG (ingesta, ask, search) |
| 14–15 | OCR sin indexar |
| 17–18 | Análisis multi-agente (JSON / SSE) |
| 16 | Abrir Swagger |

Sprints: [SPRINT_2.md](../docs/SPRINT_2.md) (chunking), [SPRINT_3.md](../docs/SPRINT_3.md) (agentes).

```powershell
.\scripts\dev-menu.ps1 -ApiBase http://localhost:8000
```

## Scripts de runtime (no eliminar)

| Archivo | Uso |
|---------|-----|
| `wait_services.py` | Entrypoint del contenedor API: espera Qdrant y Ollama |
| `ollama_pull.sh` | Job Docker `ollama-pull`: descarga modelos al arrancar |
| `smoke_test.py` | Prueba de humo no interactiva (CI o menú opción 8) |

```powershell
$env:API_BASE_URL = "http://localhost:8000"
python scripts/smoke_test.py
```
