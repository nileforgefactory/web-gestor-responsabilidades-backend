"""Endpoints de análisis de documentos con agentes."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_optional_db
from app.dependencies import get_rag_service
from app.slices.analysis.schemas import AnalisisDocumentoResponse, ProfundidadAnalisis
from app.slices.analysis.service import run_document_analysis, stream_document_analysis
from app.slices.rag.service import RagService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis", tags=["analisis"])


def _parse_normativa_ids(raw: str | None) -> list[str]:
    if not raw or not raw.strip():
        return []
    return [x.strip() for x in raw.replace(";", ",").split(",") if x.strip()]


@router.post(
    "/analyze-document",
    summary="Analizar documento (OCR + indexación + agentes)",
    description=(
        "Sube un plan (PDF/imagen/TXT), extrae texto con OCR, indexa en Qdrant, "
        "ejecuta agentes y coordinador. Con stream=true devuelve SSE."
    ),
)
async def analyze_document(
    file: UploadFile = File(...),
    collection_id: str = Form(..., min_length=1, description="Colección del plan"),
    normativa_collection_ids: str | None = Form(
        None,
        description="IDs de colecciones normativa separados por coma",
    ),
    nivel: str = Form("municipal"),
    profundidad: ProfundidadAnalisis = Form(ProfundidadAnalisis.ESTANDAR),
    entidad: str = Form(""),
    plan_id: str | None = Form(None),
    titulo_plan: str | None = Form(None),
    guardar_mysql: bool = Form(True),
    stream: bool = Form(False),
    rag: RagService = Depends(get_rag_service),
    db: AsyncSession | None = Depends(get_optional_db),
):
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
    )

    if stream:
        return StreamingResponse(
            stream_document_analysis(**kwargs),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    if guardar_mysql and db is None:
        raise HTTPException(
            503,
            "MySQL no configurado. Usa guardar_mysql=false o define MYSQL_URL.",
        )

    try:
        return await run_document_analysis(**kwargs)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logger.exception("analyze-document")
        raise HTTPException(500, str(exc)) from exc
