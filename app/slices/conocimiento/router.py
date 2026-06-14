"""Endpoints HTTP del catálogo de documentos indexados (base de conocimiento)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.openapi import RESPUESTAS_MYSQL
from app.slices.auth.dependencies import CurrentUser, WriteUser, get_current_user
from app.slices.auth.permissions import (
    allowed_collections_for_user,
    ensure_collection_access,
    is_superadmin,
)
from app.slices.conocimiento import repository as repo
from app.slices.conocimiento.schemas import (
    ConocimientoCreate,
    ConocimientoOut,
    ConocimientoUpdate,
)

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
    admin: WriteUser,
    db: AsyncSession = Depends(get_db),
) -> ConocimientoOut:
    """Crea metadatos de un documento ya indexado en Qdrant."""
    ensure_collection_access(admin, payload.coleccion_id)
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
    admin: WriteUser,
    db: AsyncSession = Depends(get_db),
) -> ConocimientoOut:
    """Actualiza estado o metadatos del documento en catálogo."""
    existing = await repo.get_doc(db, doc_id)
    if existing is None:
        raise HTTPException(404, f"Documento '{doc_id}' no encontrado")
    ensure_collection_access(admin, existing.coleccion_id)
    doc = await repo.update_doc(db, doc_id, payload)
    if doc is None:
        raise HTTPException(404, f"Documento '{doc_id}' no encontrado")
    return doc  # type: ignore[return-value]


@router.delete(
    "/{doc_id}",
    status_code=204,
    summary="Eliminar registro de documento",
    responses={**RESPUESTAS_MYSQL, 204: {"description": "Registro eliminado."}},
)
async def delete_doc(
    doc_id: str,
    admin: WriteUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Elimina el registro del catálogo (no borra vectores en Qdrant)."""
    existing = await repo.get_doc(db, doc_id)
    if existing is None:
        raise HTTPException(404, f"Documento '{doc_id}' no encontrado")
    ensure_collection_access(admin, existing.coleccion_id)
    deleted = await repo.delete_doc(db, doc_id)
    if not deleted:
        raise HTTPException(404, f"Documento '{doc_id}' no encontrado")
