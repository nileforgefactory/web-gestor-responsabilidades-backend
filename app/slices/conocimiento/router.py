"""Endpoints HTTP del catálogo de documentos indexados (base de conocimiento)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.openapi import RESPUESTAS_MYSQL
from app.slices.auth.dependencies import CurrentUser, get_current_user
from app.slices.auth.permissions import (
    allowed_collections_for_user,
    ensure_collection_access,
    is_superadmin,
)
from app.dependencies import get_rag_service
from app.slices.conocimiento import repository as repo
from app.slices.conocimiento.schemas import (
    ConocimientoCreate,
    ConocimientoOut,
    ConocimientoUpdate,
)
from app.slices.rag.service import RagService

router = APIRouter(
    prefix="/conocimiento",
    tags=["conocimiento"],
    dependencies=[Depends(get_current_user)],
)


@router.get(
    "/",
    response_model=list[ConocimientoOut],
    summary="Listar documentos del catálogo",
    response_description="Registros de documentos indexados en RAG.",
    description="Metadatos de ingesta por colección y estado. Requiere MySQL.",
    responses=RESPUESTAS_MYSQL,
)
async def list_docs(
    current_user: CurrentUser,
    coleccion_id: str | None = Query(None, description="Filtrar por colección Qdrant"),
    estado: str | None = Query(None, description="Estado del documento en catálogo"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[ConocimientoOut]:
    """Lista documentos registrados en la base de conocimiento."""
    if coleccion_id:
        ensure_collection_access(current_user, coleccion_id)
    territorio_filter = (
        None if is_superadmin(current_user) else allowed_collections_for_user(current_user)
    )
    return await repo.list_docs(
        db,
        coleccion_id=coleccion_id,
        estado=estado,
        skip=skip,
        limit=limit,
        coleccion_ids=territorio_filter,
    )  # type: ignore[return-value]


@router.get(
    "/{doc_id}",
    response_model=ConocimientoOut,
    summary="Obtener documento por ID",
    responses=RESPUESTAS_MYSQL,
)
async def get_doc(
    doc_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ConocimientoOut:
    """Devuelve un registro de documento indexado."""
    doc = await repo.get_doc(db, doc_id)
    if doc is None:
        raise HTTPException(404, f"Documento '{doc_id}' no encontrado")
    ensure_collection_access(current_user, doc.coleccion_id)
    return doc  # type: ignore[return-value]


@router.post(
    "/",
    response_model=ConocimientoOut,
    status_code=201,
    summary="Registrar documento indexado",
    response_description="Registro creado en catálogo.",
    responses={**RESPUESTAS_MYSQL, 201: {"description": "Documento registrado."}},
)
async def create_doc(
    payload: ConocimientoCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ConocimientoOut:
    """Crea metadatos de un documento ya indexado en Qdrant."""
    ensure_collection_access(current_user, payload.coleccion_id)
    return await repo.create_doc(db, payload)  # type: ignore[return-value]


@router.patch(
    "/{doc_id}",
    response_model=ConocimientoOut,
    summary="Actualizar documento",
    responses=RESPUESTAS_MYSQL,
)
async def update_doc(
    doc_id: str,
    payload: ConocimientoUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ConocimientoOut:
    """Actualiza estado o metadatos del documento en catálogo."""
    existing = await repo.get_doc(db, doc_id)
    if existing is None:
        raise HTTPException(404, f"Documento '{doc_id}' no encontrado")
    ensure_collection_access(current_user, existing.coleccion_id)
    doc = await repo.update_doc(db, doc_id, payload)
    if doc is None:
        raise HTTPException(404, f"Documento '{doc_id}' no encontrado")
    return doc  # type: ignore[return-value]


@router.post(
    "/{doc_id}/deshabilitar",
    response_model=ConocimientoOut,
    summary="Deshabilitar documento del catálogo",
    description=(
        "Marca el documento como `deshabilitado` en MySQL. "
        "Los vectores en Qdrant se eliminan para que no aparezca en búsquedas RAG. "
        "El registro permanece en catálogo para auditoría. Use `/habilitar` para revertir."
    ),
    responses=RESPUESTAS_MYSQL,
)
async def deshabilitar_doc(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    rag: RagService = Depends(get_rag_service),
) -> ConocimientoOut:
    doc = await repo.get_doc(db, doc_id)
    if doc is None:
        raise HTTPException(404, f"Documento '{doc_id}' no encontrado")
    if doc.estado == "deshabilitado":
        raise HTTPException(409, f"El documento '{doc_id}' ya está deshabilitado")

    if doc.qdrant_doc_id and doc.coleccion_id:
        try:
            await rag.repository.delete_document_chunks(
                collection_id=doc.coleccion_id,
                document_id=doc.qdrant_doc_id,
            )
        except Exception as exc:
            raise HTTPException(502, f"No se pudieron eliminar los vectores en Qdrant: {exc}") from exc

    updated = await repo.update_doc(db, doc_id, ConocimientoUpdate(estado="deshabilitado"))
    return updated  # type: ignore[return-value]


@router.post(
    "/{doc_id}/habilitar",
    response_model=ConocimientoOut,
    summary="Re-habilitar documento del catálogo",
    description=(
        "Revierte el estado de un documento `deshabilitado` a `indexado` en MySQL. "
        "No restaura vectores en Qdrant — para re-indexar usa el endpoint de ingesta."
    ),
    responses=RESPUESTAS_MYSQL,
)
async def habilitar_doc(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
) -> ConocimientoOut:
    doc = await repo.get_doc(db, doc_id)
    if doc is None:
        raise HTTPException(404, f"Documento '{doc_id}' no encontrado")
    if doc.estado != "deshabilitado":
        raise HTTPException(409, f"El documento '{doc_id}' no está deshabilitado (estado actual: {doc.estado})")

    updated = await repo.update_doc(db, doc_id, ConocimientoUpdate(estado="indexado"))
    return updated  # type: ignore[return-value]


@router.delete(
    "/{doc_id}",
    status_code=204,
    summary="Eliminar documento del catálogo y Qdrant",
    description=(
        "Elimina el registro de MySQL **y** los vectores asociados en Qdrant. "
        "Operación irreversible. Para solo desactivarlo sin borrar, usa `POST /{doc_id}/deshabilitar`."
    ),
    responses={**RESPUESTAS_MYSQL, 204: {"description": "Registro eliminado."}},
)
async def delete_doc(
    doc_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    rag: RagService = Depends(get_rag_service),
) -> None:
    """Elimina el registro del catálogo y los vectores asociados en Qdrant."""
    existing = await repo.get_doc(db, doc_id)
    if existing is None:
        raise HTTPException(404, f"Documento '{doc_id}' no encontrado")
    ensure_collection_access(current_user, existing.coleccion_id)

    if existing.qdrant_doc_id and existing.coleccion_id:
        try:
            await rag.repository.delete_document_chunks(
                collection_id=existing.coleccion_id,
                document_id=existing.qdrant_doc_id,
            )
        except Exception as exc:
            raise HTTPException(502, f"No se pudieron eliminar los vectores en Qdrant: {exc}") from exc

    deleted = await repo.delete_doc(db, doc_id)
    if not deleted:
        raise HTTPException(404, f"Documento '{doc_id}' no encontrado")
