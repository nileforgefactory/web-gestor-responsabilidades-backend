"""Persistencia opcional de resultados de análisis en MySQL."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

import re

from app.slices.planes.models import (
    ActorCompetencia,
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
    descripcion: str | None = None,
) -> str:
    """
    Inserta o actualiza plan y entidades hijas desde el resultado del análisis.

    Returns:
        ID del plan persistido (existente o nuevo UUID).
    """
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
            descripcion=descripcion[:2000] if descripcion else None,
        )
        db.add(plane)
    else:
        plane.estado = "analizado"
        plane.qdrant_doc_id = qdrant_doc_id
        plane.archivo_nombre = archivo_nombre[:500] if archivo_nombre else plane.archivo_nombre
        if descripcion:
            plane.descripcion = descripcion[:2000]

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
        _valid_tipos = ("ley", "decreto", "resolucion", "circular", "politica", "conpes", "ordenanza", "acuerdo", "otro")
        if tipo not in _valid_tipos:
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

    # Índice: nombre_actor_lower → cuántas responsabilidades lo mencionan
    responsabilidades_list = result.get("responsabilidades", [])
    def _resp_count_for(nombre: str) -> int:
        n = nombre.lower()[:20]
        return sum(
            1 for r in responsabilidades_list
            if n in str(r.get("descripcion", "")).lower()
            or n in str(r.get("titulo", "")).lower()
        )

    _valid_tipos_actor = (
        "ejecutor", "beneficiario", "financiador", "coordinador",
        "regulador", "aliado", "operador", "supervisor",
        "tomador_decision", "participante", "apoyo_tecnico", "control", "otro",
    )
    _valid_niveles = ("nacional", "departamental", "municipal", "especializado")

    def _split_competencias(raw: str) -> list[str]:
        """Divide una cadena de competencias separadas por coma, punto y coma o salto de línea."""
        items = re.split(r"[;,\n]+", raw)
        return [i.strip()[:500] for i in items if i.strip() and len(i.strip()) > 5]

    for row in result.get("actores", []):
        nombre = str(row.get("nombre", ""))[:300]
        nivel_raw = str(row.get("nivel", "") or "").lower().strip()
        sector_raw = str(row.get("sector", "") or "")[:200] or None
        actor = PlanActor(
            plan_id=pid,
            nombre=nombre,
            tipo=(
                str(row.get("tipo", "otro"))
                if str(row.get("tipo", "otro")) in _valid_tipos_actor
                else "otro"
            ),
            nivel=nivel_raw if nivel_raw in _valid_niveles else None,
            sector=sector_raw,
            resp_count=_resp_count_for(nombre),
            badge_label=nivel_raw.capitalize() if nivel_raw in _valid_niveles else None,
        )
        db.add(actor)
        await db.flush()  # obtener actor.id antes de crear competencias

        comp_raw = str(row.get("competencias", "") or "")
        for titulo_comp in _split_competencias(comp_raw):
            db.add(ActorCompetencia(
                plan_id=pid,
                actor_id=actor.id,
                titulo=titulo_comp,
                sector=sector_raw,
            ))

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
        actores_vinculados_raw = row.get("actores_vinculados", [])
        actores_json = json.dumps(
            [
                {
                    "nombre": str(a.get("nombre", ""))[:200],
                    "nivel":  str(a.get("nivel",  ""))[:50],
                    "tipo":   str(a.get("tipo",   ""))[:50],
                }
                for a in actores_vinculados_raw
                if a.get("nombre")
            ],
            ensure_ascii=False,
        )
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
                actores_vinculados=actores_json,
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
