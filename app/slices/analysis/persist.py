"""Persistencia opcional de resultados de análisis en MySQL."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.slices.planes.models import (
    Brecha,
    MatrizCompetencia,
    Plane,
    PlanActor,
    PlanNorma,
    Responsabilidad,
)


async def persist_analysis(
    db: AsyncSession,
    *,
    plan_id: str | None,
    titulo: str,
    nivel: str,
    archivo_nombre: str,
    qdrant_doc_id: str,
    result: dict[str, Any],
) -> str:
    pid = plan_id or str(uuid.uuid4())
    plane = await db.get(Plane, pid)
    if plane is None:
        plane = Plane(
            id=pid,
            titulo=titulo[:500],
            nivel=nivel,
            estado="analizado",
            archivo_nombre=archivo_nombre[:500] if archivo_nombre else None,
            qdrant_doc_id=qdrant_doc_id,
        )
        db.add(plane)
    else:
        plane.estado = "analizado"
        plane.qdrant_doc_id = qdrant_doc_id
        plane.archivo_nombre = archivo_nombre[:500] if archivo_nombre else plane.archivo_nombre

    for row in result.get("responsabilidades", []):
        db.add(
            Responsabilidad(
                plan_id=pid,
                titulo=str(row.get("titulo", ""))[:500],
                descripcion=row.get("descripcion"),
                sector=row.get("sector"),
                tipo=str(row.get("tipo", "P"))[:1] or "P",
                referencia_legal=row.get("referencia_legal"),
            )
        )

    for row in result.get("leyes", []):
        tipo = str(row.get("tipo", "ley")).lower()
        if tipo not in ("ley", "decreto", "resolucion", "circular", "otro"):
            tipo = "otro"
        db.add(
            PlanNorma(
                plan_id=pid,
                norma_codigo=str(row.get("codigo", ""))[:100],
                titulo=str(row.get("titulo", row.get("codigo", "Norma")))[:500],
                articulos=str(row.get("articulos", ""))[:200],
                extracto=str(row.get("relevancia", ""))[:2000] or None,
                tipo=tipo,
            )
        )

    for row in result.get("actores", []):
        db.add(
            PlanActor(
                plan_id=pid,
                nombre=str(row.get("nombre", ""))[:300],
                tipo=(
                    str(row.get("tipo", "otro"))
                    if str(row.get("tipo", "otro"))
                    in ("principal", "concurrente", "subsidiario", "otro")
                    else "otro"
                ),
            )
        )

    for row in result.get("brechas", []):
        tipo = str(row.get("tipo", "critica"))
        if tipo not in ("critica", "duplicidad", "indefinido", "sin_responsable"):
            tipo = "critica"
        sev = str(row.get("severidad", "media"))
        if sev not in ("alta", "media", "baja"):
            sev = "media"
        db.add(
            Brecha(
                plan_id=pid,
                titulo=str(row.get("titulo", ""))[:500],
                descripcion=row.get("descripcion"),
                tipo=tipo,
                severidad=sev,
                referencia_legal=row.get("norma_base"),
            )
        )

    for row in result.get("matriz", []):
        def _pcsn(v: Any) -> str:
            s = str(v or "N").upper()[:1]
            return s if s in ("P", "C", "S", "N") else "N"

        brecha = str(row.get("brecha", "ok"))
        if brecha not in ("ok", "critica", "duplicidad", "indefinido"):
            brecha = "ok"
        db.add(
            MatrizCompetencia(
                plan_id=pid,
                competencia=str(row.get("competencia", ""))[:300],
                ley_base=str(row.get("ley_base", ""))[:200],
                nacion=_pcsn(row.get("nacion")),
                departamento=_pcsn(row.get("departamento")),
                municipio=_pcsn(row.get("municipio")),
                especializado=_pcsn(row.get("especializado")),
                brecha=brecha,
            )
        )

    resp_n = len(result.get("responsabilidades", []))
    ley_n = len(result.get("leyes", []))
    act_n = len(result.get("actores", []))
    bre_n = len(result.get("brechas", []))
    plane.resp_total = resp_n
    plane.leyes_total = ley_n
    plane.actores_total = act_n
    plane.brechas_total = bre_n

    await db.flush()
    return pid
