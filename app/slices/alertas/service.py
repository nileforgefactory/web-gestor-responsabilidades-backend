"""
Servicio de alertas normativas.
Compara las normas de un plan contra el RAG para detectar
normas que pueden haber sido modificadas o derogadas.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.slices.alertas.models import AlertaNormativa
from app.slices.common.territorio import collection_id_from_territorio
from app.slices.conocimiento import repository as conocimiento_repo
from app.slices.planes.models import PlanNorma
from app.slices.rag.service import RagService

logger = logging.getLogger(__name__)

_KEYWORDS_DEROGACION = [
    "derogado", "derogada", "derogados",
    "modificado", "modificada",
    "sustituido", "sustituida",
    "subrogado", "reemplazado",
]


async def check_normas_actualizadas(
    db: AsyncSession,
    rag: RagService,
    plan_id: str,
) -> list[AlertaNormativa]:
    """
    Para cada norma del plan, busca en el RAG si hay indicios de
    modificación o derogación. Crea y persiste alertas nuevas.
    """
    stmt = select(PlanNorma).where(PlanNorma.plan_id == plan_id)
    result = await db.execute(stmt)
    normas: list[PlanNorma] = list(result.scalars().all())

    if not normas:
        return []

    alertas_creadas: list[AlertaNormativa] = []
    thr = rag.settings.rag_default_score_threshold
    collection_ids = await conocimiento_repo.distinct_coleccion_ids(db)
    if not collection_ids:
        collection_ids = [collection_id_from_territorio(None)]

    for norma in normas:
        codigo = norma.norma_codigo or norma.titulo[:50]
        query = f"{codigo} modificación derogación actualización"

        try:
            search_result = await rag.search(
                query=query,
                collection_ids=collection_ids,
                top_k=3,
                score_threshold=thr,
            )
        except Exception as exc:
            logger.warning("Error buscando norma '%s': %s", codigo, exc)
            continue

        for chunk in search_result.chunks:
            texto = chunk.text.lower()
            if any(kw in texto for kw in _KEYWORDS_DEROGACION):
                alerta = AlertaNormativa(
                    plan_id=plan_id,
                    tipo="modificacion",
                    titulo=f"{codigo} puede haber sido modificada",
                    descripcion=chunk.text[:500],
                    norma_ref=codigo,
                    severidad="alta" if norma.relevancia >= 80 else "media",
                )
                db.add(alerta)
                alertas_creadas.append(alerta)
                break  # solo una alerta por norma

    if alertas_creadas:
        await db.flush()

    return alertas_creadas


async def get_alertas_plan(
    db: AsyncSession,
    plan_id: str,
    solo_no_leidas: bool = False,
) -> list[AlertaNormativa]:
    stmt = select(AlertaNormativa).where(AlertaNormativa.plan_id == plan_id)
    if solo_no_leidas:
        stmt = stmt.where(AlertaNormativa.leida.is_(False))
    stmt = stmt.order_by(AlertaNormativa.creado_en.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def marcar_leidas(db: AsyncSession, ids: list[int]) -> int:
    from sqlalchemy import update
    stmt = (
        update(AlertaNormativa)
        .where(AlertaNormativa.id.in_(ids))
        .values(leida=True)
    )
    result = await db.execute(stmt)
    return result.rowcount or 0
