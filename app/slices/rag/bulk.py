"""Ingesta masiva de documentos en una colección RAG."""

from __future__ import annotations

import asyncio
import logging

from fastapi import HTTPException, UploadFile

from app.core.config import Settings
from app.slices.common.batch_upload import ArchivoCargado, leer_archivos_cargados, validar_lote_archivos
from app.slices.rag.extract import (
    derive_document_id_from_filename,
    extract_document_from_bytes,
    extract_title,
)
from app.slices.rag.schemas import IngestArchivoResultado, IngestMasivaResponse
from app.slices.rag.service import RagService

logger = logging.getLogger(__name__)


def _document_id_unico(base: str, usados: set[str]) -> str:
    if base not in usados:
        usados.add(base)
        return base
    i = 2
    while True:
        candidato = f"{base}-{i}"
        if candidato not in usados:
            usados.add(candidato)
            return candidato
        i += 1


async def ingestir_archivos_masivo(
    *,
    service: RagService,
    settings: Settings,
    collection_id: str,
    uploads: list[UploadFile],
    chunk_size: int,
    chunk_overlap: int,
    document_id_prefix: str | None,
    continuar_si_error: bool,
) -> IngestMasivaResponse:
    validar_lote_archivos(uploads, settings)
    cargados = await leer_archivos_cargados(uploads, settings)

    ids_usados: set[str] = set()
    trabajo: list[tuple[ArchivoCargado, str]] = []
    for item in cargados:
        base_id = derive_document_id_from_filename(item.nombre)
        if document_id_prefix:
            base_id = f"{document_id_prefix.strip()}-{base_id}"
        doc_id = _document_id_unico(base_id, ids_usados)
        trabajo.append((item, doc_id))

    sem = asyncio.Semaphore(max(1, settings.bulk_ingest_concurrency))

    async def procesar(item: ArchivoCargado, doc_id: str) -> IngestArchivoResultado:
        async with sem:
            try:
                extraccion = await extract_document_from_bytes(
                    item.contenido,
                    item.nombre,
                    settings=settings,
                )
                ingesta = await service.ingest_text(
                    collection_id=collection_id,
                    document_id=doc_id,
                    content=extraccion.text,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    title=extract_title(item.nombre),
                    source_filename=item.nombre,
                )
                return IngestArchivoResultado(
                    nombre_archivo=item.nombre,
                    document_id=doc_id,
                    exito=True,
                    chunks_indexados=ingesta.chunks_indexed,
                    metodo_extraccion=extraccion.extraction_method.value,
                    caracteres_extraidos=extraccion.char_count,
                )
            except Exception as exc:
                logger.warning(
                    "Fallo ingesta masiva archivo=%s: %s",
                    item.nombre,
                    exc,
                    exc_info=True,
                )
                return IngestArchivoResultado(
                    nombre_archivo=item.nombre,
                    document_id=doc_id,
                    exito=False,
                    error=str(exc),
                )

    resultados = await asyncio.gather(*(procesar(item, doc_id) for item, doc_id in trabajo))

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
    chunks_totales = sum(r.chunks_indexados for r in resultados if r.exito)

    return IngestMasivaResponse(
        collection_id=collection_id,
        total_archivos=len(resultados),
        exitosos=exitosos,
        fallidos=len(resultados) - exitosos,
        chunks_totales=chunks_totales,
        resultados=list(resultados),
    )
