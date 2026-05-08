"""Endpoints HTTP para la Base de Conocimiento."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.slices.conocimiento import repository as repo
from app.slices.conocimiento.schemas import (
    ConocimientoCreate,
    ConocimientoOut,
    ConocimientoUpdate,
)

router = APIRouter(prefix="/conocimiento", tags=["conocimiento"])


@router.get("/", response_model=list[ConocimientoOut], summary="Listar documentos indexados")
async def list_docs(
    coleccion_id: str | None = Query(None),
    estado:       str | None = Query(None),
    skip:  int = Query(0,   ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[ConocimientoOut]:
    return await repo.list_docs(db, coleccion_id=coleccion_id, estado=estado, skip=skip, limit=limit)  # type: ignore[return-value]


@router.get("/{doc_id}", response_model=ConocimientoOut)
async def get_doc(doc_id: str, db: AsyncSession = Depends(get_db)) -> ConocimientoOut:
    doc = await repo.get_doc(db, doc_id)
    if doc is None:
        raise HTTPException(404, f"Documento '{doc_id}' no encontrado")
    return doc  # type: ignore[return-value]


@router.post("/", response_model=ConocimientoOut, status_code=201, summary="Registrar documento indexado")
async def create_doc(
    payload: ConocimientoCreate, db: AsyncSession = Depends(get_db)
) -> ConocimientoOut:
    return await repo.create_doc(db, payload)  # type: ignore[return-value]


@router.patch("/{doc_id}", response_model=ConocimientoOut, summary="Actualizar estado de un documento")
async def update_doc(
    doc_id: str, payload: ConocimientoUpdate, db: AsyncSession = Depends(get_db)
) -> ConocimientoOut:
    doc = await repo.update_doc(db, doc_id, payload)
    if doc is None:
        raise HTTPException(404, f"Documento '{doc_id}' no encontrado")
    return doc  # type: ignore[return-value]


@router.delete("/{doc_id}", status_code=204, summary="Eliminar registro de documento")
async def delete_doc(doc_id: str, db: AsyncSession = Depends(get_db)) -> None:
    deleted = await repo.delete_doc(db, doc_id)
    if not deleted:
        raise HTTPException(404, f"Documento '{doc_id}' no encontrado")
