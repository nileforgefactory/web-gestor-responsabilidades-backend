from __future__ import annotations

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.slices.conocimiento.models import BaseConocimiento
from app.slices.conocimiento.schemas import ConocimientoCreate, ConocimientoUpdate


async def distinct_coleccion_ids(db: AsyncSession) -> list[str]:
    """IDs de colección lógica presentes en el catálogo MySQL."""
    stmt = select(distinct(BaseConocimiento.coleccion_id))
    result = await db.execute(stmt)
    return sorted(r[0] for r in result.all() if r[0])


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
    from app.slices.conocimiento.schemas import territorio_for_db

    payload = data.model_dump()
    terr = payload.pop("territorio", None)
    if terr is not None:
        payload["territorio"] = territorio_for_db(terr)
    doc = BaseConocimiento(**payload)
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
    from app.slices.conocimiento.schemas import territorio_for_db

    for field, value in data.model_dump(exclude_none=True).items():
        if field == "territorio" and value is not None:
            setattr(doc, field, territorio_for_db(value))
        else:
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
