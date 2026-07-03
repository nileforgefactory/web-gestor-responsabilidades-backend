"""Pipeline SGR — Modo 1: evaluar plan y generar candidatos de proyectos."""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.slices.planes.models import Brecha, Plane
from app.slices.sgr.agents.agente_elegibilidad import evaluar_elegibilidad
from app.slices.sgr.models import ProyectoSGR
from app.slices.sgr.schemas import (
    EvaluarPlanResponse,
    ProyectoCandidatoResponse,
)

logger = logging.getLogger(__name__)

# ── Scoring ────────────────────────────────────────────────────────────────────

_SEVERIDAD_SCORE = {"alta": 1.0, "media": 0.6, "baja": 0.3}

_PESO_SEVERIDAD = 0.30
_PESO_ALINEACION = 0.25
_PESO_ELEGIBILIDAD = 0.25
_PESO_VIABILIDAD = 0.20

# Umbral de score para fuentes con mayor probabilidad histórica de aprobación
_VIABILIDAD_POR_FUENTE = {
    "inversion_local": 0.80,    # El alcalde aprueba, alta autonomía
    "asignacion_directa": 0.75,
    "inversion_regional": 0.55, # Depende de OCAD departamental
    "ctei": 0.45,               # Convocatoria competitiva
    "paz": 0.50,
    "ambiental": 0.55,
    "no_aplica": 0.0,
}

_SEMAFORO_UMBRALES = [
    (0.70, "verde",    "Alta viabilidad — proceder con formulación MGA"),
    (0.45, "amarillo", "Viabilidad media — revisar condiciones antes de formular"),
    (0.0,  "rojo",     "Baja viabilidad — considerar alternativas"),
]


def _calcular_score(
    severidad: str,
    confidence: float,
    elegible: bool,
    fuente: str,
) -> dict[str, float]:
    s_severidad = _SEVERIDAD_SCORE.get(severidad, 0.3)
    s_alineacion = min(max(confidence, 0.0), 1.0)
    s_elegibilidad = 1.0 if elegible else 0.0
    s_viabilidad = _VIABILIDAD_POR_FUENTE.get(fuente, 0.4)

    total = (
        s_severidad * _PESO_SEVERIDAD
        + s_alineacion * _PESO_ALINEACION
        + s_elegibilidad * _PESO_ELEGIBILIDAD
        + s_viabilidad * _PESO_VIABILIDAD
    )
    return {
        "score_sgr": round(total, 4),
        "score_severidad": round(s_severidad, 4),
        "score_alineacion": round(s_alineacion, 4),
        "score_elegibilidad": round(s_elegibilidad, 4),
        "score_viabilidad": round(s_viabilidad, 4),
    }


def _semaforo(score: float) -> tuple[str, str]:
    for umbral, color, label in _SEMAFORO_UMBRALES:
        if score >= umbral:
            return color, label
    return "rojo", "Baja viabilidad"


# ── Pipeline principal ─────────────────────────────────────────────────────────

async def evaluar_plan_sgr(
    *,
    plan_id: str,
    db: AsyncSession,
    http: httpx.AsyncClient,
    settings: Settings,
    top_n: int = 10,
    solo_elegibles: bool = False,
    guardar: bool = True,
) -> EvaluarPlanResponse:
    """
    Modo 1: dado un plan analizado, evalúa sus brechas y devuelve candidatos SGR.

    Flujo:
    1. Carga plan y usuario/municipio desde DB
    2. Recupera todas las brechas del plan
    3. Evalúa elegibilidad SGR por brecha (agente_elegibilidad, concurrente)
    4. Calcula scoring ponderado
    5. Ordena por score y devuelve TOP N
    6. Persiste ProyectoSGR en DB si guardar=True
    """
    advertencias: list[str] = []

    # ── 1. Cargar plan ─────────────────────────────────────────────────────
    result = await db.execute(select(Plane).where(Plane.id == plan_id))
    plane = result.scalar_one_or_none()
    if plane is None:
        raise ValueError(f"Plan '{plan_id}' no encontrado")

    if plane.estado not in ("analizado", "en-proceso"):
        advertencias.append(
            f"El plan está en estado '{plane.estado}'; "
            "se recomienda esperar a que el análisis esté completo."
        )

    # ── 2. Recuperar brechas ───────────────────────────────────────────────
    brechas_result = await db.execute(
        select(Brecha).where(Brecha.plan_id == plan_id)
    )
    brechas = brechas_result.scalars().all()

    if not brechas:
        advertencias.append("El plan no tiene brechas detectadas. Ejecuta el análisis primero.")
        return EvaluarPlanResponse(
            plan_id=plan_id,
            municipio_codigo=None,
            categoria_municipio=None,
            total_brechas=0,
            total_elegibles=0,
            total_no_elegibles=0,
            proyectos_candidatos=[],
            advertencias=advertencias,
        )

    # ── 3. Datos del municipio (extraídos del plan; se enriquecerán con User) ─
    # Por ahora extraemos lo disponible del plan; el User con divipola/nbi/icld
    # se añade cuando el endpoint tiene acceso al current_user.
    datos_municipio: dict = {
        "nombre_municipio": plane.entidad or plane.titulo,
        "divipola": None,
        "categoria_municipio": None,
        "nbi": None,
        "icld": None,
        "departamento": None,
        "region_geografica": "Andes",  # default — se actualiza con User
    }

    # ── 4. Evaluar elegibilidad concurrentemente (máx. 5 en paralelo) ─────
    semaphore = asyncio.Semaphore(5)

    async def _evaluar_con_semaforo(brecha: Brecha) -> dict:
        async with semaphore:
            return await evaluar_elegibilidad(
                brecha={
                    "id": brecha.id,
                    "titulo": brecha.titulo,
                    "descripcion": brecha.descripcion or "",
                    "sector": brecha.sector if hasattr(brecha, "sector") else "",
                    "severidad": brecha.severidad,
                    "tipo_detallado": brecha.tipo_detallado or brecha.tipo,
                    "referencia_legal": brecha.referencia_legal or "",
                    "recomendacion": brecha.recomendacion or "",
                },
                datos_municipio=datos_municipio,
                http=http,
                settings=settings,
            )

    resultados = await asyncio.gather(
        *[_evaluar_con_semaforo(b) for b in brechas],
        return_exceptions=True,
    )

    # ── 5. Construir candidatos con scoring ────────────────────────────────
    # Mapa brecha_id → confidence_score (si existe en el modelo)
    brechas_map = {b.id: b for b in brechas}

    candidatos: list[ProyectoCandidatoResponse] = []
    elegibles = 0
    no_elegibles = 0

    for resultado in resultados:
        if isinstance(resultado, Exception):
            logger.warning("[evaluar_plan_sgr] Error en evaluación: %s", resultado)
            no_elegibles += 1
            continue

        brecha_id = resultado.get("brecha_id")
        brecha_obj = brechas_map.get(brecha_id)
        if brecha_obj is None:
            continue

        elegible = resultado.get("elegible", False)
        if elegible:
            elegibles += 1
        else:
            no_elegibles += 1

        if solo_elegibles and not elegible:
            continue

        # confidence_score no existe aún en el modelo Brecha; usar 0.7 por defecto
        confidence = float(getattr(brecha_obj, "confidence_score", 0.7) or 0.7)

        scores = _calcular_score(
            severidad=resultado.get("brecha_severidad", "baja"),
            confidence=confidence,
            elegible=elegible,
            fuente=resultado.get("fuente_recomendada", "no_aplica"),
        )

        color, label = _semaforo(scores["score_sgr"])

        nombre_proyecto = (
            f"{resultado.get('tipo_inversion', resultado.get('brecha_titulo', ''))}"
            f" — {plane.entidad or ''}"
        ).strip(" —")

        candidato = ProyectoCandidatoResponse(
            id=None,
            brecha_id=brecha_id,
            brecha_titulo=resultado.get("brecha_titulo", ""),
            brecha_severidad=resultado.get("brecha_severidad", "baja"),
            nombre=nombre_proyecto,
            sector_sgr=resultado.get("sector_sgr", ""),
            subsector=resultado.get("subsector"),
            tipo_inversion=resultado.get("tipo_inversion", ""),
            fuente_recomendada=resultado.get("fuente_recomendada", "no_aplica"),
            fuente_label=resultado.get("fuente_label", ""),
            razon_elegibilidad=resultado.get("razon", ""),
            condiciones=resultado.get("condiciones", []),
            semaforo=color,
            semaforo_label=label,
            **scores,
        )
        candidatos.append(candidato)

    # ── 6. Ordenar por score y limitar a TOP N ─────────────────────────────
    candidatos.sort(key=lambda c: c.score_sgr, reverse=True)
    top_candidatos = candidatos[:top_n]

    # ── 7. Persistir en DB ─────────────────────────────────────────────────
    if guardar and top_candidatos:
        # Eliminar proyectos previos en modo descubrimiento para este plan
        proyectos_existentes = await db.execute(
            select(ProyectoSGR).where(
                ProyectoSGR.plan_id == plan_id,
                ProyectoSGR.modo == "descubrimiento",
            )
        )
        for p in proyectos_existentes.scalars().all():
            await db.delete(p)

        for c in top_candidatos:
            brecha_obj = brechas_map.get(c.brecha_id)
            proyecto = ProyectoSGR(
                id=str(uuid4()),
                plan_id=plan_id,
                brecha_id=c.brecha_id,
                municipio_codigo=datos_municipio.get("divipola") or "00000000",
                nombre=c.nombre,
                descripcion_problema=brecha_obj.descripcion if brecha_obj else None,
                sector_sgr=c.sector_sgr,
                subsector_sgr=c.subsector,
                tipo_inversion=c.tipo_inversion,
                fuente_sgr=c.fuente_recomendada if c.fuente_recomendada != "no_aplica" else None,
                score_sgr=c.score_sgr,
                score_severidad=c.score_severidad,
                score_alineacion=c.score_alineacion,
                score_elegibilidad=c.score_elegibilidad,
                score_viabilidad=c.score_viabilidad,
                elegible=c.score_elegibilidad > 0,
                razon_elegibilidad=c.razon_elegibilidad,
                estado="borrador",
                modo="descubrimiento",
            )
            db.add(proyecto)
            c.id = proyecto.id

        await db.commit()

    if not candidatos and not advertencias:
        advertencias.append(
            "Ninguna brecha del plan cumple criterios de elegibilidad SGR básicos. "
            "Verifica que el plan haya sido analizado con profundidad 'estandar' o 'profundo'."
        )

    return EvaluarPlanResponse(
        plan_id=plan_id,
        municipio_codigo=datos_municipio.get("divipola"),
        categoria_municipio=datos_municipio.get("categoria_municipio"),
        total_brechas=len(brechas),
        total_elegibles=elegibles,
        total_no_elegibles=no_elegibles,
        proyectos_candidatos=top_candidatos,
        advertencias=advertencias,
    )
