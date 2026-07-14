"""CRUD de normas territoriales del indexer + consulta para el scraper."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.slices.background_scraper.models import NormaTerritorial

logger = logging.getLogger(__name__)


async def listar(db: AsyncSession, *, incluir_inactivas: bool = True) -> list[NormaTerritorial]:
    stmt = select(NormaTerritorial).order_by(NormaTerritorial.creado_en.desc())
    if not incluir_inactivas:
        stmt = stmt.where(NormaTerritorial.activo.is_(True))
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def crear(
    db: AsyncSession,
    *,
    codigo: str,
    territorio: str | None,
    prioridad: int,
    descripcion: str | None,
) -> NormaTerritorial:
    norma = NormaTerritorial(
        codigo=codigo.strip(),
        territorio=(territorio or None),
        prioridad=prioridad,
        descripcion=(descripcion or None),
    )
    db.add(norma)
    await db.commit()
    await db.refresh(norma)
    return norma


async def eliminar(db: AsyncSession, norma_id: str) -> bool:
    res = await db.execute(select(NormaTerritorial).where(NormaTerritorial.id == norma_id))
    norma = res.scalar_one_or_none()
    if norma is None:
        return False
    await db.delete(norma)
    await db.commit()
    return True


async def codigos_activos(prioridad_max: int) -> list[str]:
    """Códigos de normas territoriales activas (para el indexer, contexto background)."""
    from app.core.database import mysql_available, session_scope

    if not mysql_available():
        return []
    try:
        async with session_scope() as db:
            res = await db.execute(
                select(NormaTerritorial.codigo).where(
                    NormaTerritorial.activo.is_(True),
                    NormaTerritorial.prioridad <= prioridad_max,
                )
            )
            return [c for c in res.scalars().all() if c]
    except Exception as exc:  # pragma: no cover - defensivo
        logger.warning("[territorial] no se pudieron leer normas territoriales: %s", exc)
        return []
