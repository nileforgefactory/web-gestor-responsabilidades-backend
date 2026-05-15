"""Extracción masiva de texto (sin indexar en Qdrant)."""

from __future__ import annotations

import asyncio
import logging

from fastapi import HTTPException, UploadFile

from app.core.config import Settings
from app.slices.common.batch_upload import ArchivoCargado, leer_archivos_cargados, validar_lote_archivos
from app.slices.ocr.schemas import (
    ExtraccionArchivoResultado,
    ExtraccionMasivaResponse,
    MetodoExtraccion,
)
from app.slices.rag.extract import extract_document_from_bytes

logger = logging.getLogger(__name__)


async def extraer_archivos_masivo(
    *,
    settings: Settings,
    uploads: list[UploadFile],
    incluir_texto: bool,
    continuar_si_error: bool,
) -> ExtraccionMasivaResponse:
    validar_lote_archivos(uploads, settings)
    cargados = await leer_archivos_cargados(uploads, settings)

    sem = asyncio.Semaphore(max(1, settings.bulk_ingest_concurrency))

    async def procesar(item: ArchivoCargado) -> ExtraccionArchivoResultado:
        async with sem:
            try:
                extraccion = await extract_document_from_bytes(
                    item.contenido,
                    item.nombre,
                    settings=settings,
                )
                texto: str | None = None
                if incluir_texto:
                    texto = extraccion.text
                return ExtraccionArchivoResultado(
                    nombre_archivo=item.nombre,
                    exito=True,
                    metodo_extraccion=MetodoExtraccion(extraccion.extraction_method.value),
                    paginas=extraccion.page_count,
                    caracteres=extraccion.char_count,
                    paginas_ocr=extraccion.ocr_pages,
                    paginas_nativas=extraccion.native_pages,
                    confianza_ocr_promedio=extraccion.ocr_confidence_avg,
                    texto=texto,
                )
            except Exception as exc:
                logger.warning(
                    "Fallo extracción masiva archivo=%s: %s",
                    item.nombre,
                    exc,
                    exc_info=True,
                )
                return ExtraccionArchivoResultado(
                    nombre_archivo=item.nombre,
                    exito=False,
                    error=str(exc),
                )

    resultados = list(await asyncio.gather(*(procesar(c) for c in cargados)))

    if not continuar_si_error and any(not r.exito for r in resultados):
        fallidos = [r.nombre_archivo for r in resultados if not r.exito]
        raise HTTPException(
            status_code=422,
            detail={
                "mensaje": "Uno o más archivos fallaron y continuar_si_error=false.",
                "archivos_fallidos": fallidos,
                "resultados": [r.model_dump() for r in resultados],
            },
        )

    exitosos = sum(1 for r in resultados if r.exito)
    return ExtraccionMasivaResponse(
        total_archivos=len(resultados),
        exitosos=exitosos,
        fallidos=len(resultados) - exitosos,
        resultados=resultados,
    )
