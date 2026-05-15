"""Extracción de texto sin indexar en Qdrant (prueba OCR y pre-análisis)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import get_settings
from app.slices.documents.bulk import extraer_archivos_masivo
from app.slices.ocr.schemas import (
    ExtraccionDocumentoResponse,
    ExtraccionMasivaResponse,
    MetodoExtraccion,
)
from app.slices.rag.extract import extract_document_from_upload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documentos"])

_FORMATOS_ACEPTADOS = (
    "PDF, TXT, Markdown (.md) e imágenes (PNG, JPG, TIFF, WEBP). "
    "Los PDF escaneados usan OCR automático cuando el texto nativo es insuficiente."
)


@router.post(
    "/extract",
    response_model=ExtraccionDocumentoResponse,
    summary="Extraer texto de un documento (OCR si aplica)",
    description=(
        "Devuelve el texto completo del archivo sin indexarlo en Qdrant. "
        "Útil para validar OCR antes del análisis con agentes. " + _FORMATOS_ACEPTADOS
    ),
)
async def extract_document(
    file: UploadFile = File(..., description="Documento a procesar"),
) -> ExtraccionDocumentoResponse:
    try:
        result = await extract_document_from_upload(file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Fallo extracción de documento")
        detail = str(exc)
        if "tesseract" in detail.lower() or "poppler" in detail.lower():
            detail += (
                " Comprueba que el contenedor API incluya Tesseract y Poppler "
                "(ver docs/SPRINT_0.md)."
            )
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
    summary="Extracción masiva de documentos",
    description=(
        "Procesa varios archivos en paralelo (OCR si aplica) sin indexar en Qdrant. "
        "Por defecto no devuelve el texto completo (solo metadatos); usa incluir_texto=true "
        "si necesitas el contenido en la respuesta. " + _FORMATOS_ACEPTADOS
    ),
)
async def extract_documents_bulk(
    files: list[UploadFile] = File(
        ...,
        description="Varios archivos con el mismo nombre de campo 'files'",
    ),
    incluir_texto: bool = Form(
        False,
        description="Si true, incluye el texto completo de cada archivo en la respuesta",
    ),
    continuar_si_error: bool = Form(
        True,
        description="Si es false, responde 422 ante el primer archivo fallido",
    ),
) -> ExtraccionMasivaResponse:
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
