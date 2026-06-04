import asyncio
import json
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.config import Settings, get_settings
from app.core.logging_config import configure_logging
from app.core.database import dispose_engine, init_db
from app.core.session_store import get_session_store, init_session_store
from app.db import models_registry  # noqa: F401
from app.db.migrate import run_migrations
from app.dependencies import get_rag_service
from app.slices.rag.router import router as rag_router
from app.slices.planes.router import router as planes_router
from app.slices.conocimiento.router import router as conocimiento_router
from app.slices.documents.router import router as documents_router
from app.slices.analysis.router import router as analysis_router
from app.slices.scraper.router import router as scraper_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Arranque: colección Qdrant y tablas MySQL opcionales; cierre de clientes al apagar."""
    # ── RAG (Qdrant + Ollama) ──
    rag_service = get_rag_service()
    await rag_service.ensure_collection()

    # ── MySQL (opcional) ──
    settings = get_settings()
    if settings.mysql_url:
        init_db(
            settings.mysql_url,
            pool_pre_ping=settings.mysql_pool_pre_ping,
            pool_size=settings.scraper_max_concurrency + 4,
            max_overflow=settings.scraper_max_concurrency + 6,
        )
        if settings.effective_mysql_run_migrations:
            await asyncio.to_thread(run_migrations)

    # ── Redis (opcional — sesiones SSE) ──
    if settings.redis_url:
        init_session_store(settings.redis_url)

    yield

    await rag_service.close()
    await dispose_engine()
    store = get_session_store()
    if store:
        await store.close()


def _model_tag_present(registry: list[str], want: str) -> bool:
    """True si el modelo solicitado (o su base sin tag) está en el listado de Ollama."""
    target = want.strip().lower()
    base = target.split(":")[0]
    for raw in registry:
        n = raw.strip().lower()
        if not n:
            continue
        if n == target or n.split(":")[0] == base or n.startswith(base + ":"):
            return True
    return False


def _blocking_readiness(settings: Settings) -> tuple[dict[str, Any], bool]:
    """Comprueba Qdrant y Ollama de forma síncrona (ejecutar en hilo desde async)."""
    snapshot: dict[str, Any] = {
        "app_env": settings.app_env,
        "checks": {},
    }

    healthy = True

    q_url = settings.qdrant_url.rstrip("/") + "/collections"
    try:
        urllib.request.urlopen(q_url, timeout=6)
        snapshot["checks"]["qdrant"] = {"reachable": True, "url": q_url}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        healthy = False
        snapshot["checks"]["qdrant"] = {
            "reachable": False,
            "url": q_url,
            "error": repr(exc),
        }

    if not settings.use_ollama:
        snapshot["checks"]["ollama"] = {
            "enabled": False,
            "embedding_model_registered": True,
            "chat_model_registered": True,
            "installed_models_sample": [],
        }
        snapshot["healthy"] = healthy
        return snapshot, healthy

    tags_url = settings.ollama_base_url.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(tags_url, timeout=8) as r:
            parsed = json.load(r)
        models_payload = parsed.get("models") if isinstance(parsed, dict) else None
        names: list[str] = []
        if isinstance(models_payload, list):
            for row in models_payload:
                if isinstance(row, dict):
                    nm = row.get("name")
                    if isinstance(nm, str):
                        names.append(nm)

        emb_ok = _model_tag_present(names, settings.ollama_embedding_model)
        chat_ok = _model_tag_present(names, settings.ollama_chat_model)
        reachable = True
        ollama_healthy = emb_ok and chat_ok
        snapshot["checks"]["ollama"] = {
            "enabled": True,
            "daemon_reachable": reachable,
            "tags_url": tags_url,
            "embedding_model": settings.ollama_embedding_model,
            "embedding_model_registered": emb_ok,
            "chat_model": settings.ollama_chat_model,
            "chat_model_registered": chat_ok,
            "installed_models_sample": names[:12],
            "installed_count": len(names),
        }
        if not ollama_healthy:
            healthy = False

    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        healthy = False
        snapshot["checks"]["ollama"] = {
            "enabled": True,
            "daemon_reachable": False,
            "tags_url": tags_url,
            "error": repr(exc),
        }

    snapshot["healthy"] = healthy
    return snapshot, healthy


class StripUtf8JsonBOMMiddleware(BaseHTTPMiddleware):
    """Clientes UTF-8 con BOM antes de `{` inicial rompen `json.loads` (error típico en body posición 1)."""

    async def dispatch(self, request: Request, call_next):
        ctype = request.headers.get("content-type", "")
        if (
            request.method in ("POST", "PUT", "PATCH")
            and "application/json" in ctype.lower()
        ):
            body = await request.body()
            bom = b"\xef\xbb\xbf"
            if body.startswith(bom):
                body = body[len(bom) :]

            async def receive():
                return {"type": "http.request", "body": body, "more_body": False}

            request = Request(request.scope, receive)
        response = await call_next(request)
        return response


settings = get_settings()

_DOCS_SUMMARY_ES = """\
**RAG 100% local** (Docker): ingesta PDF/TXT/MD, embeddings y chat con Ollama, vectores en Qdrant.

- **JSON valido obligatorio**: comillas **`"`** ASCII (no tipograficas `'...'`). En Swagger usa el ejemplo y **solo comillas rectas**.
- **Swagger**: grupo RAG, ejemplos prellenados; `/rag/ingest-file` es multipart.
- **Estado**: `GET /health/ready`.
"""

configure_logging(settings)

openapi_tags_docs = [
    {
        "name": "salud",
        "description": "Comprobaciones ligeras para depuracion (Swagger, Compose, soporte local).",
    },
    {"name": "rag",          "description": "Ingesta, busqueda, contexto para agentes y preguntas con modelo local."},
    {"name": "planes",       "description": "CRUD de planes de desarrollo (requiere MySQL)."},
    {"name": "conocimiento", "description": "Registro de documentos indexados en la base de conocimiento RAG (requiere MySQL)."},
    {
        "name": "documentos",
        "description": "Extracción de texto y OCR de archivos (sin indexar en Qdrant).",
    },
    {
        "name": "analisis",
        "description": "Análisis multi-agente de planes: OCR, indexación, loop coordinador y SSE.",
    },
    {
        "name": "scraper",
        "description": "Búsqueda de normativa en internet, validación IA e indexación en RAG.",
    },
]

app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    summary="API-RAG demo",
    description=_DOCS_SUMMARY_ES,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=openapi_tags_docs,
    swagger_ui_parameters={
        "defaultModelsExpandDepth": 2,
        "docExpansion": "list",
        "tryItOutEnabled": True,
    },
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["*"],
)
app.add_middleware(StripUtf8JsonBOMMiddleware)


@app.exception_handler(RequestValidationError)
async def request_validation_hints(_request: Request, exc: RequestValidationError):
    """Añade pistas en español cuando el cuerpo JSON es inválido (comillas, BOM)."""
    errs = exc.errors()
    payload: dict[str, Any] = {"detail": errs}
    if errs and isinstance(errs[0], dict):
        row = errs[0]
        if row.get("type") == "json_invalid":
            payload["hint"] = (
                "JSON invalido: solo comillas dobles ASCII (\"clave\":\"valor\"). "
                "Evita comillas simples alrededor del objeto, BOM al inicio, o pegar "
                "dos comandos en una sola linea (headers/DATA truncados). "
                "PowerShell: .\\scripts\\dev-menu.ps1 (opción 12) o JSON con comillas simples externas."
            )
    return JSONResponse(status_code=422, content=payload)


app.include_router(rag_router,          prefix="/api/v1")
app.include_router(planes_router,       prefix="/api/v1")
app.include_router(conocimiento_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(analysis_router, prefix="/api/v1")
app.include_router(scraper_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """Redirige la raíz a la documentación Swagger."""
    return RedirectResponse(url="/docs", status_code=307)


@app.get(
    "/health",
    tags=["salud"],
    summary="Ping mínimo de la API",
    response_description="Estado básico sin comprobar dependencias.",
)
async def health() -> dict[str, str]:
    """Responde si el proceso HTTP está activo (no valida Qdrant ni Ollama)."""
    return {"status": "ok", "env": settings.app_env}


@app.get(
    "/health/ready",
    tags=["salud"],
    summary="Preparación para ingesta y análisis",
    response_description="JSON con checks de Qdrant y Ollama; 503 si no está listo.",
    description=(
        "Comprueba Qdrant, daemon Ollama y modelos de embeddings/chat registrados. "
        "Ejecutar antes de ingest, ask o analyze-document desde Swagger."
    ),
    responses={
        200: {"description": "Sistema listo (healthy=true)."},
        503: {"description": "Alguna dependencia no está lista (healthy=false)."},
    },
)
async def health_ready() -> JSONResponse:
    """Valida dependencias críticas antes de operaciones costosas."""

    snapshot, healthy = await asyncio.to_thread(_blocking_readiness, get_settings())

    snapshot["swagger_hint"] = (
        "Si healthy=false tras docker compose up, revisa docker logs api-rag-ollama-pull "
        "y el panel de errores Swagger (502/504 = red/tiempo)."
    )

    status_code = 200 if healthy else 503
    return JSONResponse(status_code=status_code, content=snapshot)
