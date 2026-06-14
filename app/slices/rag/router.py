"""Endpoints HTTP del slice RAG (ingesta, búsqueda, ask)."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_optional_db
from app.core.openapi import RESPUESTAS_RAG
from app.slices.auth.dependencies import CurrentUser, WriteUser, get_current_user
from app.slices.auth.permissions import (
    ensure_collection_access,
    ensure_collections_access,
    allowed_collections_for_user,
    is_superadmin,
)
from app.dependencies import get_rag_service
from app.slices.conocimiento import repository as conocimiento_repo
from app.slices.rag.bulk import ingestir_archivos_masivo
from app.slices.rag.extract import (
    derive_document_id_from_filename,
    extract_document_from_upload,
    extract_title,
)
from app.slices.rag.schemas import (
    AgentContextRequest,
    AgentContextResponse,
    AskRequest,
    AskResponse,
    EstrategiaChunk,
    IngestMasivaResponse,
    IngestTextRequest,
    IngestTextResponse,
    ColeccionesListResponse,
    RagSearchRequest,
    RagSearchResponse,
)
from app.slices.rag.service import RagService

logger = logging.getLogger(__name__)

_ASK_BODY_EXAMPLES: dict[str, dict] = {
    "demo_demo_local": {
        "summary": "Pregunta demo (colección demo_local)",
        "description": (
            "Requiere ingesta previa con collection_id=demo_local "
            "(p. ej. sample_documents/demo_policies.md)."
        ),
        "value": {
            "collection_ids": ["demo_local"],
            "user_message": "Cual es el SLA de primera respuesta para un incidente P1?",
            "top_k": 5,
        },
    },
}

router = APIRouter(
    prefix="/rag",
    tags=["rag"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "/colecciones",
    response_model=ColeccionesListResponse,
    summary="Listar colecciones lógicas disponibles",
    description=(
        "Devuelve los ``collection_id`` con datos en Qdrant (chunks y documentos) "
        "y marca cuáles existen en el catálogo MySQL. "
        "Las colecciones lógicas comparten la colección física configurada en Qdrant."
    ),
    responses=RESPUESTAS_RAG,
)
async def listar_colecciones(
    current_user: CurrentUser,
    service: RagService = Depends(get_rag_service),
    db: AsyncSession | None = Depends(get_optional_db),
) -> ColeccionesListResponse:
    """Inventario de namespaces de ingesta (p. ej. COLOMBIA, COLOMBIA_CAUCA, demo_local)."""
    await service.ensure_collection()
    catalog_ids: set[str] = set()
    if db is not None:
        catalog_ids = set(await conocimiento_repo.distinct_coleccion_ids(db))
    response = await service.list_logical_collections(catalog_collection_ids=catalog_ids)
    if not is_superadmin(current_user):
        allowed = allowed_collections_for_user(current_user)
        filtered = [c for c in response.colecciones if c.collection_id.upper() in allowed]
        response.colecciones = filtered
        response.total = len(filtered)
    return response


def _upstream_http(exc: BaseException, *, code: int) -> HTTPException:
    """Convierte errores de red/upstream en HTTPException con mensaje orientativo."""
    return HTTPException(
        status_code=code,
        detail=(
            f"No se pudo completar la operación (upstream): {exc!s}. "
            "Sugerencia: GET /health/ready y logs docker api-rag-ollama / api-rag-api."
        ),
    )


@router.post(
    "/ingest-text",
    response_model=IngestTextResponse,
    summary="Ingestar texto plano en Qdrant",
    response_description="Documento fragmentado, embebido e indexado.",
    description=(
        "Recibe contenido UTF-8 en JSON, aplica chunking (fijo o adaptativo), "
        "genera embeddings con Ollama y almacena vectores en Qdrant."
    ),
    responses=RESPUESTAS_RAG,
)
async def ingest_text(
    payload: IngestTextRequest,
    admin: WriteUser,
    service: RagService = Depends(get_rag_service),
) -> IngestTextResponse:
    """Indexa texto JSON en la colección indicada."""
    ensure_collection_access(admin, payload.collection_id)
    await service.ensure_collection()
    try:
        return await service.ingest_text(
            collection_id=payload.collection_id,
            document_id=payload.document_id,
            content=payload.content,
            chunk_size=payload.chunk_size,
            chunk_overlap=payload.chunk_overlap,
            title=payload.document_id,
            source_filename=None,
            chunk_strategy=payload.chunk_strategy.value,
        )
    except httpx.HTTPError as exc:
        raise _upstream_http(exc, code=502) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Fallo ingest_text")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/ingest-file",
    response_model=IngestTextResponse,
    summary="Ingestar archivo (PDF, TXT, MD, imagen)",
    response_description="Texto extraído (OCR si aplica) e indexado en Qdrant.",
    description=(
        "Multipart: sube un archivo, extrae texto (OCR automático en PDFs escaneados), "
        "aplica chunking y indexa en la colección. "
        "Parámetro `chunk_strategy`: `fixed` o `adaptive` (recomendado)."
    ),
    responses=RESPUESTAS_RAG,
)
async def ingest_file(
    admin: WriteUser,
    collection_id: str = Form(..., min_length=1, description="ID lógico de la colección Qdrant"),
    document_id: str | None = Form(
        None,
        description="ID del documento; si se omite se deriva del nombre del archivo",
    ),
    chunk_size: int = Form(700, ge=200, le=8000, description="Tamaño objetivo de chunk (modo fixed)"),
    chunk_overlap: int = Form(120, ge=0, le=2000, description="Solapamiento entre chunks"),
    chunk_strategy: EstrategiaChunk = Form(
        EstrategiaChunk.ADAPTATIVO,
        description="Estrategia de fragmentación: fixed | adaptive",
    ),
    file: UploadFile = File(..., description="Archivo a indexar"),
    service: RagService = Depends(get_rag_service),
) -> IngestTextResponse:
    """Extrae texto del archivo, fragmenta e indexa en Qdrant."""
    ensure_collection_access(admin, collection_id)
    await service.ensure_collection()
    try:
        extraccion = await extract_document_from_upload(file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    filename = extraccion.filename
    doc_id = (document_id or "").strip() or derive_document_id_from_filename(filename)
    title = extract_title(filename)
    try:
        return await service.ingest_text(
            collection_id=collection_id,
            document_id=doc_id,
            content=extraccion.text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            title=title,
            source_filename=filename,
            chunk_strategy=chunk_strategy.value,
            extraction_method=extraccion.extraction_method.value,
        )
    except httpx.HTTPError as exc:
        raise _upstream_http(exc, code=502) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Fallo ingest_file")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/ingest-files",
    response_model=IngestMasivaResponse,
    summary="Ingesta masiva de documentos",
    response_description="Resumen por archivo y total de chunks indexados.",
    description=(
        "Sube varios archivos a la misma colección. OCR automático cuando corresponde. "
        "Límites: `BULK_MAX_FILES`, `BULK_MAX_FILE_BYTES`. "
        "Concurrencia controlada por `BULK_INGEST_CONCURRENCY`."
    ),
    responses=RESPUESTAS_RAG,
)
async def ingest_files_bulk(
    admin: WriteUser,
    collection_id: str = Form(..., min_length=1, description="Colección destino"),
    files: list[UploadFile] = File(
        ...,
        description="Repetir el campo `files` por cada archivo en multipart",
    ),
    chunk_size: int = Form(700, ge=200, le=8000),
    chunk_overlap: int = Form(120, ge=0, le=2000),
    chunk_strategy: EstrategiaChunk = Form(
        EstrategiaChunk.ADAPTATIVO,
        description="Estrategia de chunking aplicada a todos los archivos",
    ),
    document_id_prefix: str | None = Form(
        None,
        description="Prefijo opcional para document_id (evita colisiones de nombre)",
    ),
    continuar_si_error: bool = Form(
        True,
        description="Si es false, aborta con 422 al primer archivo fallido",
    ),
    service: RagService = Depends(get_rag_service),
) -> IngestMasivaResponse:
    """Procesa múltiples archivos en paralelo limitado e indexa cada uno."""
    ensure_collection_access(admin, collection_id)
    await service.ensure_collection()
    settings = get_settings()
    try:
        return await ingestir_archivos_masivo(
            service=service,
            settings=settings,
            collection_id=collection_id,
            uploads=files,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            chunk_strategy=chunk_strategy.value,
            document_id_prefix=document_id_prefix,
            continuar_si_error=continuar_si_error,
        )
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise _upstream_http(exc, code=502) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Fallo ingest_files_bulk")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/search",
    response_model=RagSearchResponse,
    summary="Búsqueda semántica en colecciones",
    response_description="Chunks ordenados por score de similitud coseno.",
    description=(
        "Embede la consulta con Ollama y recupera los `top_k` fragmentos más similares "
        "de las colecciones indicadas, filtrando por `score_threshold`."
    ),
    responses=RESPUESTAS_RAG,
)
async def search(
    payload: RagSearchRequest,
    current_user: CurrentUser,
    service: RagService = Depends(get_rag_service),
) -> RagSearchResponse:
    """Búsqueda vectorial sin invocar el modelo de chat."""
    ensure_collections_access(current_user, payload.collection_ids)
    await service.ensure_collection()
    try:
        return await service.search(
            query=payload.query,
            collection_ids=payload.collection_ids,
            top_k=payload.top_k,
            score_threshold=payload.score_threshold,
        )
    except httpx.HTTPError as exc:
        raise _upstream_http(exc, code=502) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Fallo search")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/agent-context",
    response_model=AgentContextResponse,
    summary="Construir contexto RAG para agentes externos",
    response_description="Bloque de texto ensamblado y citas de chunks usados.",
    description=(
        "Recupera chunks relevantes y devuelve un contexto listo para inyectar "
        "en prompts de agentes orquestados fuera de este endpoint."
    ),
    responses=RESPUESTAS_RAG,
)
async def agent_context(
    payload: AgentContextRequest,
    current_user: CurrentUser,
    service: RagService = Depends(get_rag_service),
) -> AgentContextResponse:
    """Ensambla contexto + metadatos de citas sin generar respuesta final."""
    ensure_collections_access(current_user, payload.collection_ids)
    await service.ensure_collection()
    try:
        return await service.build_agent_context(
            user_message=payload.user_message,
            collection_ids=payload.collection_ids,
            top_k=payload.top_k,
        )
    except httpx.HTTPError as exc:
        raise _upstream_http(exc, code=502) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Fallo agent_context")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Pregunta con RAG + modelo local (Ollama)",
    response_description="Respuesta generada con citas y chunks utilizados.",
    description=(
        "Recupera evidencia en Qdrant y genera respuesta con Ollama usando solo "
        "el contexto recuperado. Puede tardar varios minutos en CPU. "
        "Use JSON con comillas dobles ASCII (ver ejemplos)."
    ),
    responses=RESPUESTAS_RAG,
)
async def rag_ask(
    current_user: CurrentUser,
    payload: AskRequest = Body(
        openapi_examples=_ASK_BODY_EXAMPLES,
        description="Consulta conversacional con evidencia recuperada + Ollama.",
    ),
    service: RagService = Depends(get_rag_service),
) -> AskResponse:
    """Pipeline RAG completo: búsqueda + chat con restricción a evidencia."""
    ensure_collections_access(current_user, payload.collection_ids)
    await service.ensure_collection()
    try:
        return await service.ask(
            user_message=payload.user_message,
            collection_ids=payload.collection_ids,
            top_k=payload.top_k,
            score_threshold=payload.score_threshold,
        )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail=(
                f"Tiempo agotado hablando con Ollama ({exc!s}). "
                "Reintente; modelos grandes en CPU requieren espera prolongada."
            ),
        ) from exc
    except httpx.HTTPError as exc:
        raise _upstream_http(exc, code=502) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Fallo rag_ask")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
