"""Validación y lectura de lotes multipart."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, UploadFile

from app.core.config import Settings


@dataclass(frozen=True)
class ArchivoCargado:
    """Bytes y nombre de un archivo ya validado para procesamiento por lotes."""

    nombre: str
    contenido: bytes


def validar_lote_archivos(archivos: list[UploadFile], settings: Settings) -> None:
    """
    Comprueba cantidad máxima de archivos por petición.

    Raises:
        HTTPException: 400 si la lista está vacía o excede ``bulk_max_files``.
    """
    if not archivos:
        raise HTTPException(status_code=400, detail="Debes enviar al menos un archivo.")
    if len(archivos) > settings.bulk_max_files:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Máximo {settings.bulk_max_files} archivos por solicitud "
                f"(recibidos: {len(archivos)})."
            ),
        )


async def leer_archivos_cargados(
    uploads: list[UploadFile],
    settings: Settings,
) -> list[ArchivoCargado]:
    """
    Lee todos los uploads en memoria aplicando límite de tamaño por archivo.

    Raises:
        HTTPException: 400 archivo vacío, 413 si supera ``bulk_max_file_bytes``.
    """
    validar_lote_archivos(uploads, settings)
    cargados: list[ArchivoCargado] = []
    for upload in uploads:
        nombre = (upload.filename or "document").strip()
        raw = await upload.read()
        if not raw:
            raise HTTPException(status_code=400, detail=f"Archivo vacío: {nombre}")
        if len(raw) > settings.bulk_max_file_bytes:
            limite_mb = settings.bulk_max_file_bytes // (1024 * 1024)
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Archivo demasiado grande: {nombre} "
                    f"({len(raw)} bytes). Límite: {limite_mb} MiB."
                ),
            )
        cargados.append(ArchivoCargado(nombre=nombre, contenido=raw))
    return cargados
