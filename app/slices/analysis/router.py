"""Endpoints de análisis multi-agente de planes de desarrollo."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db, get_optional_db
from app.core.openapi import RESPUESTAS_ANALISIS
from app.dependencies import get_rag_service
from app.slices.analysis.pdf_export import generar_pdf_analisis
from app.slices.analysis.schemas import AnalisisDocumentoResponse, ProfundidadAnalisis
from app.slices.analysis.service import cancel_analysis, run_document_analysis, stream_document_analysis
from app.slices.rag.service import RagService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/analysis",
    tags=["analisis"],
)


def _parse_normativa_ids(raw: str | None) -> list[str]:
    """Parsea IDs de colección normativa separados por coma o punto y coma."""
    if not raw or not raw.strip():
        return []
    return [x.strip() for x in raw.replace(";", ",").split(",") if x.strip()]


@router.post(
    "/analyze-document",
    summary="Analizar plan: OCR → indexar → agentes → coordinador",
    response_description="JSON con extracciones o flujo SSE si stream=true.",
    description=(
        "**Pipeline completo:** extracción (OCR), indexación en `collection_id`, "
        "agentes (responsabilidades, leyes, actores; brechas si profundo), "
        "loop del coordinador (excepto profundidad básica), matriz (estándar/profundo) "
        "y persistencia opcional en MySQL.\n\n"
        "- `stream=true`: respuesta `text/event-stream` con eventos de progreso.\n"
        "- `normativa_collection_ids`: colecciones RAG adicionales (leyes), separadas por coma.\n"
        "- `guardar_mysql=false` si no hay MYSQL_URL configurado."
    ),
    responses={
        **RESPUESTAS_ANALISIS,
        200: {
            "description": (
                "JSON con resultados (`stream=false`) o flujo SSE (`stream=true`, "
                "Content-Type: text/event-stream)."
            ),
            "model": AnalisisDocumentoResponse,
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string", "description": "Eventos SSE (type: log, agent_done, done, ...)"},
                },
            },
        },
    },
)
async def analyze_document(
    file: UploadFile = File(..., description="Plan en PDF, imagen, TXT o MD"),
    collection_id: str = Form(
        ...,
        min_length=1,
        description="Colección Qdrant donde se indexa el plan analizado",
    ),
    normativa_collection_ids: str | None = Form(
        None,
        description="Colecciones de normativa vigente (ej: normas_legales), separadas por coma",
    ),
    nivel: str = Form(
        "municipal",
        description="Contexto territorial: nacional | departamental | municipal | sectorial",
    ),
    profundidad: ProfundidadAnalisis = Form(
        ProfundidadAnalisis.ESTANDAR,
        description="basico | estandar | profundo — controla agentes, loop y matriz",
    ),
    entidad: str = Form("", description="Nombre de la entidad territorial analizada"),
    plan_id: str | None = Form(
        None,
        description="UUID de plan existente en MySQL; si se omite se genera uno nuevo al guardar",
    ),
    titulo_plan: str | None = Form(None, description="Título al persistir en MySQL"),
    guardar_mysql: bool = Form(
        True,
        description="Persistir responsabilidades, leyes, actores, brechas y matriz",
    ),
    max_iteraciones: int = Form(
        None,
        description="Iteraciones máximas del coordinador (sobreescribe settings). None = usa el valor por defecto.",
    ),
    stream: bool = Form(
        False,
        description="true = SSE en vivo; false = JSON único al finalizar",
    ),
    rag: RagService = Depends(get_rag_service),
    db: AsyncSession | None = Depends(get_optional_db),
) -> Response:
    """
    Orquesta el análisis completo de un documento de plan de desarrollo.

    Requiere Ollama y Qdrant operativos (`GET /health/ready`).
    """
    settings = get_settings()
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Archivo vacío")

    filename = file.filename or "documento.pdf"
    normativa_ids = _parse_normativa_ids(normativa_collection_ids)

    kwargs = dict(
        rag=rag,
        settings=settings,
        raw=raw,
        filename=filename,
        collection_id=collection_id,
        normativa_collection_ids=normativa_ids,
        nivel=nivel,
        profundidad=profundidad.value,
        entidad=entidad,
        plan_id=plan_id,
        titulo_plan=titulo_plan,
        guardar_mysql=guardar_mysql,
        db=db if guardar_mysql and db is not None else None,
        max_iteraciones=max_iteraciones,
    )

    if guardar_mysql and db is None:
        raise HTTPException(
            503,
            "MySQL no configurado. Usa guardar_mysql=false o define MYSQL_URL.",
        )

    if stream:
        return StreamingResponse(
            stream_document_analysis(**kwargs),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    try:
        return await run_document_analysis(**kwargs)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("analyze-document")
        raise HTTPException(500, str(exc)) from exc


class SaveResultRequest(BaseModel):
    titulo:        str
    nombre_corto:  str | None = None
    nivel:         str = "municipal"
    entidad:       str = ""
    periodo:       str | None = None
    archivo_nombre: str | None = None
    qdrant_doc_id: str | None = None
    result:        dict


@router.post(
    "/save-result",
    summary="Persistir en MySQL el resultado de un análisis ya ejecutado",
    status_code=200,
)
async def save_analysis_result(
    body: SaveResultRequest,
    db: AsyncSession | None = Depends(get_optional_db),
) -> dict:
    """Guarda responsabilidades, leyes, actores, brechas y matriz de un análisis previo."""
    from app.slices.analysis.persist import persist_analysis

    if db is None:
        raise HTTPException(503, "MySQL no configurado")

    plan_id = await persist_analysis(
        db,
        plan_id=None,
        titulo=body.titulo,
        nivel=body.nivel,
        archivo_nombre=body.archivo_nombre or "",
        qdrant_doc_id=body.qdrant_doc_id or "",
        result=body.result,
    )
    await db.commit()
    return {"plan_id": plan_id, "guardado": True}


@router.post(
    "/session/{session_id}/cancel",
    summary="Cancelar un análisis en curso",
    status_code=200,
)
async def cancel_session(session_id: str) -> dict[str, str]:
    """Cancela la tarea asyncio del pipeline asociada al session_id."""
    cancelled = cancel_analysis(session_id)
    if cancelled:
        return {"status": "cancelled", "session_id": session_id}
    return {"status": "not_found", "session_id": session_id}


@router.get(
    "/export-pdf/{plan_id}",
    summary="Exportar análisis completo de un plan a PDF",
    description=(
        "Genera un informe PDF detallado con responsabilidades, marco legal, actores, "
        "brechas (críticas, duplicidades, sin responsable), matriz de competencias y "
        "recomendaciones para decisiones administrativas."
    ),
    responses={
        200: {
            "description": "PDF del informe de análisis",
            "content": {"application/pdf": {}},
        },
        404: {"description": "Plan no encontrado"},
        503: {"description": "MySQL no configurado"},
    },
)
async def export_pdf(
    plan_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Genera y devuelve el PDF de análisis completo del plan indicado.

    Requiere MySQL configurado (el plan debe estar guardado).
    """
    from app.slices.planes import repository as repo

    plane = await repo.get_plane(db, plan_id)
    if plane is None:
        raise HTTPException(404, f"Plan '{plan_id}' no encontrado")

    # Serializar el ORM a dict compatible con pdf_export
    from app.slices.planes.schemas import PlanDetail
    detail = PlanDetail.model_validate(plane)
    plan_dict = detail.model_dump()

    try:
        pdf_bytes = generar_pdf_analisis(plan_dict)
    except Exception as exc:
        logger.exception("Error generando PDF para plan %s", plan_id)
        raise HTTPException(500, f"Error al generar PDF: {exc}") from exc

    titulo_safe = (detail.titulo or "plan")[:50].replace(" ", "_").replace("/", "-")
    filename = f"analisis_{titulo_safe}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
