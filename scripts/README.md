# Scripts del proyecto

## Menú interactivo (recomendado)

```powershell
.\scripts\dev-menu.ps1
```

Integra arranque Docker, salud, humo, ingesta (simple y masiva), RAG ask/search y extracción OCR.

Parámetro opcional:

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
