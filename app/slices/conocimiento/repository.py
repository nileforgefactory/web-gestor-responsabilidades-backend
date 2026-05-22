from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.slices.conocimiento.models import BaseConocimiento
from app.slices.conocimiento.schemas import ConocimientoCreate, ConocimientoUpdate


async def list_docs(
    db: AsyncSession,
    *,
    coleccion_id: str | None = None,
    estado: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[BaseConocimiento]:
    stmt = (
        select(BaseConocimiento)
        .order_by(BaseConocimiento.creado_en.desc())
        .offset(skip)
        .limit(limit)
    )
    if coleccion_id:
        stmt = stmt.where(BaseConocimiento.coleccion_id == coleccion_id)
    if estado:
        stmt = stmt.where(BaseConocimiento.estado == estado)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_doc(db: AsyncSession, doc_id: str) -> BaseConocimiento | None:
    return await db.get(BaseConocimiento, doc_id)


async def create_doc(db: AsyncSession, data: ConocimientoCreate) -> BaseConocimiento:
    doc = BaseConocimiento(**data.model_dump())
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    return doc


async def update_doc(
    db: AsyncSession, doc_id: str, data: ConocimientoUpdate
) -> BaseConocimiento | None:
    doc = await db.get(BaseConocimiento, doc_id)
    if doc is None:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(doc, field, value)
    await db.flush()
    await db.refresh(doc)
    return doc


async def delete_doc(db: AsyncSession, doc_id: str) -> bool:
    doc = await db.get(BaseConocimiento, doc_id)
    if doc is None:
        return False
    await db.delete(doc)
    return True
