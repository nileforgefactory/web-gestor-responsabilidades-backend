"""Endpoints de extracción de texto (OCR) sin indexación en Qdrant."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.config import get_settings
from app.core.openapi import RESPUESTAS_ESTANDAR
from app.slices.auth.dependencies import WriteUser, get_current_user, require_write
from app.slices.documents.bulk import extraer_archivos_masivo
from app.slices.ocr.schemas import (
    ExtraccionDocumentoResponse,
    ExtraccionMasivaResponse,
    MetodoExtraccion,
)
from app.slices.rag.extract import extract_document_from_upload

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/documents",
    tags=["documentos"],
    dependencies=[Depends(get_current_user), Depends(require_write)],
)

_FORMATOS = (
    "Formatos: PDF, TXT, Markdown (.md), PNG, JPG, TIFF, WEBP. "
    "PDF escaneado → OCR automático si el texto nativo es insuficiente."
)


@router.post(
    "/extract",
    response_model=ExtraccionDocumentoResponse,
    summary="Extraer texto de un documento",
    response_description="Texto completo y metadatos de extracción (método, páginas, OCR).",
    description=(
        "No indexa en Qdrant. Útil para validar calidad OCR antes de ingesta o análisis. "
        + _FORMATOS
    ),
    responses=RESPUESTAS_ESTANDAR,
)
async def extract_document(
    file: UploadFile = File(..., description="Documento a procesar"),
) -> ExtraccionDocumentoResponse:
    """Ejecuta extracción nativa u OCR y devuelve el texto íntegro."""
    try:
        result = await extract_document_from_upload(file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Fallo extracción de documento")
        detail = str(exc)
        if "tesseract" in detail.lower() or "poppler" in detail.lower():
            detail += " Comprueba Tesseract y Poppler en la imagen Docker (docs/SPRINT_0.md)."
        raise HTTPException(status_code=500, detail=detail) from exc

    return ExtraccionDocumentoResponse(
        texto=result.text,
        nombre_archivo=result.filename,
        metodo_extraccion=MetodoExtraccion(result.extraction_method.value),
        paginas=result.page_count,
        caracteres=result.char_count,
        paginas_ocr=result.ocr_pages,
        paginas_nativas=result.native_pages,
        confianza_ocr_promedio=result.ocr_confidence_avg,
    )


@router.post(
    "/extract-files",
    response_model=ExtraccionMasivaResponse,
    summary="Extracción masiva sin indexar",
    response_description="Resultado por archivo (éxito, método, caracteres).",
    description=(
        "Procesa varios archivos en paralelo limitado. "
        "`incluir_texto=false` (default) evita respuestas muy pesadas. " + _FORMATOS
    ),
    responses=RESPUESTAS_ESTANDAR,
)
async def extract_documents_bulk(
    files: list[UploadFile] = File(
        ...,
        description="Campo `files` repetido por cada archivo",
    ),
    incluir_texto: bool = Form(
        False,
        description="Incluir texto completo en cada ítem de la respuesta",
    ),
    continuar_si_error: bool = Form(
        True,
        description="Si false, responde 422 al primer archivo fallido",
    ),
) -> ExtraccionMasivaResponse:
    """Extrae texto de un lote sin pasar por Qdrant."""
    settings = get_settings()
    try:
        return await extraer_archivos_masivo(
            settings=settings,
            uploads=files,
            incluir_texto=incluir_texto,
            continuar_si_error=continuar_si_error,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Fallo extract-files")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
