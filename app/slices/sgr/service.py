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
from app.slices.sgr.agents.agente_duplicidad import verificar_duplicidad
from app.slices.sgr.agents.agente_elegibilidad import evaluar_elegibilidad
from app.slices.sgr.agents.agente_evaluador import evaluar_proyecto
from app.slices.sgr.agents.agente_mga import generar_ficha_mga
from app.slices.sgr.models import FichaMGA, ProyectoSGR
from app.slices.sgr.schemas import (
    DiagnosticoDimension,
    EvaluarPlanResponse,
    EvaluarProyectoResponse,
    ProyectoCandidatoResponse,
    SimilarRagItem,
    SubflujoInclusion,
    VerificarDuplicidadResponse,
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


# ── M4: Generación Ficha MGA ───────────────────────────────────────────────────

async def generar_ficha_mga_service(
    *,
    proyecto_id: str,
    db: AsyncSession,
    rag,
    http: httpx.AsyncClient,
    settings: Settings,
    forzar_regeneracion: bool = False,
    top_chunks_plan: int = 5,
) -> FichaMGA:
    """
    Genera (o regenera) la Ficha MGA de un ProyectoSGR existente.

    Flujo:
    1. Carga ProyectoSGR y su Brecha origen
    2. Recupera fragmentos del Plan de Desarrollo vía RAG
    3. Llama al agente_mga para generar las 4 secciones
    4. Persiste en la tabla fichas_mga (upsert)
    5. Actualiza estado del proyecto a 'pre_validado' si campos_completos == 4
    """
    from app.slices.rag.service import RagService  # import local para evitar circular

    # ── 1. Cargar proyecto ─────────────────────────────────────────────────
    result = await db.execute(select(ProyectoSGR).where(ProyectoSGR.id == proyecto_id))
    proyecto = result.scalar_one_or_none()
    if proyecto is None:
        raise ValueError(f"Proyecto '{proyecto_id}' no encontrado")

    # ── 2. Verificar si ya existe ficha y no se fuerza regeneración ─────
    ficha_existente_result = await db.execute(
        select(FichaMGA).where(FichaMGA.proyecto_id == proyecto_id)
    )
    ficha_existente = ficha_existente_result.scalar_one_or_none()
    if ficha_existente and not forzar_regeneracion:
        return ficha_existente

    # ── 3. Cargar brecha origen ────────────────────────────────────────────
    brecha_dict: dict = {}
    if proyecto.brecha_id:
        brecha_result = await db.execute(
            select(Brecha).where(Brecha.id == proyecto.brecha_id)
        )
        brecha_obj = brecha_result.scalar_one_or_none()
        if brecha_obj:
            brecha_dict = {
                "titulo": brecha_obj.titulo,
                "descripcion": brecha_obj.descripcion or "",
                "severidad": brecha_obj.severidad,
                "referencia_legal": brecha_obj.referencia_legal or "",
                "recomendacion": brecha_obj.recomendacion or "",
            }

    # ── 4. RAG: fragmentos del plan de desarrollo ──────────────────────────
    plan_chunks: list[str] = []
    if proyecto.plan_id:
        query_text = (
            f"{proyecto.nombre} {proyecto.sector_sgr or ''} "
            f"{brecha_dict.get('titulo', '')} inversión pública"
        ).strip()
        try:
            resultados_rag = await rag.search(query=query_text, limit=top_chunks_plan)
            plan_chunks = [
                r.get("text", "") if isinstance(r, dict) else str(r)
                for r in resultados_rag
                if r
            ]
        except Exception as exc:
            logger.warning("[generar_ficha_mga] RAG search falló: %s", exc)

    # ── 5. Datos municipio desde el proyecto ───────────────────────────────
    datos_municipio = {
        "divipola": proyecto.municipio_codigo,
        "nombre_municipio": proyecto.nombre,
        "categoria_municipio": None,
        "nbi": None,
        "icld": None,
        "departamento": None,
        "region_geografica": None,
    }

    proyecto_dict = {
        "id": proyecto.id,
        "nombre": proyecto.nombre,
        "sector_sgr": proyecto.sector_sgr or "",
        "tipo_inversion": proyecto.tipo_inversion or "",
        "fuente_sgr": proyecto.fuente_sgr or "inversion_local",
        "razon_elegibilidad": proyecto.razon_elegibilidad or "",
        "score_sgr": proyecto.score_sgr,
    }

    # ── 6. Llamar al agente MGA ────────────────────────────────────────────
    resultado_mga = await generar_ficha_mga(
        proyecto=proyecto_dict,
        brecha=brecha_dict,
        datos_municipio=datos_municipio,
        plan_chunks=plan_chunks,
        http=http,
        settings=settings,
    )

    # ── 7. Persistir ficha (upsert) ────────────────────────────────────────
    if ficha_existente:
        ficha_existente.identificacion = resultado_mga.get("identificacion")
        ficha_existente.preparacion = resultado_mga.get("preparacion")
        ficha_existente.evaluacion = resultado_mga.get("evaluacion")
        ficha_existente.programacion = resultado_mga.get("programacion")
        ficha_existente.campos_completos = resultado_mga.get("campos_completos", 0)
        ficha_existente.modelo_usado = resultado_mga.get("modelo_usado")
        ficha = ficha_existente
    else:
        ficha = FichaMGA(
            proyecto_id=proyecto_id,
            identificacion=resultado_mga.get("identificacion"),
            preparacion=resultado_mga.get("preparacion"),
            evaluacion=resultado_mga.get("evaluacion"),
            programacion=resultado_mga.get("programacion"),
            campos_completos=resultado_mga.get("campos_completos", 0),
            modelo_usado=resultado_mga.get("modelo_usado"),
        )
        db.add(ficha)

    # ── 8. Avanzar estado del proyecto si la ficha está completa ──────────
    if resultado_mga.get("campos_completos", 0) == 4:
        if proyecto.estado in ("borrador", "diagnosticado"):
            proyecto.estado = "pre_validado"

    await db.commit()
    await db.refresh(ficha)
    logger.info(
        "[generar_ficha_mga] Proyecto %s → %d/4 secciones, estado=%s",
        proyecto_id,
        ficha.campos_completos,
        proyecto.estado,
    )
    return ficha


# ── M3: Verificación de Duplicidad ────────────────────────────────────────────

async def verificar_duplicidad_service(
    *,
    proyecto_id: str,
    db: AsyncSession,
    rag,
    http: httpx.AsyncClient,
    settings: Settings,
) -> VerificarDuplicidadResponse:
    """
    Verifica duplicidad de un ProyectoSGR contra el Mapa de Inversiones (RAG).

    Flujo:
    1. Carga ProyectoSGR y su Brecha
    2. Llama al agente_duplicidad (RAG semántico + LLM)
    3. Persiste resultado en proyecto.resultado_duplicidad (JSON)
    4. Si bloqueado → estado = 'borrador' con advertencia en diagnostico_mga
    5. Devuelve VerificarDuplicidadResponse
    """
    import json

    # ── 1. Cargar proyecto ─────────────────────────────────────────────────
    result = await db.execute(select(ProyectoSGR).where(ProyectoSGR.id == proyecto_id))
    proyecto = result.scalar_one_or_none()
    if proyecto is None:
        raise ValueError(f"Proyecto '{proyecto_id}' no encontrado")

    # ── 2. Cargar brecha ───────────────────────────────────────────────────
    brecha_dict: dict = {}
    if proyecto.brecha_id:
        brecha_result = await db.execute(
            select(Brecha).where(Brecha.id == proyecto.brecha_id)
        )
        brecha_obj = brecha_result.scalar_one_or_none()
        if brecha_obj:
            brecha_dict = {
                "titulo": brecha_obj.titulo,
                "descripcion": brecha_obj.descripcion or "",
                "severidad": brecha_obj.severidad,
            }

    datos_municipio = {
        "divipola": proyecto.municipio_codigo,
        "nombre_municipio": proyecto.nombre,
        "categoria_municipio": None,
    }

    proyecto_dict = {
        "id": proyecto.id,
        "nombre": proyecto.nombre,
        "sector_sgr": proyecto.sector_sgr or "",
        "tipo_inversion": proyecto.tipo_inversion or "",
        "fuente_sgr": proyecto.fuente_sgr or "inversion_local",
        "municipio_codigo": proyecto.municipio_codigo,
    }

    # ── 3. Agente de duplicidad ────────────────────────────────────────────
    resultado = await verificar_duplicidad(
        proyecto=proyecto_dict,
        brecha=brecha_dict,
        datos_municipio=datos_municipio,
        rag=rag,
        http=http,
        settings=settings,
    )

    # ── 4. Persistir resultado en el proyecto ──────────────────────────────
    resultado_persistible = {
        k: v for k, v in resultado.items() if k != "similares_rag"
    }
    proyecto.resultado_duplicidad = resultado_persistible

    if resultado.get("bloqueado"):
        proyecto.diagnostico_mga = {
            "alerta": "DUPLICIDAD_ALTA",
            "mensaje": resultado.get("recomendacion", ""),
        }

    await db.commit()

    similares_rag = [
        SimilarRagItem(**s) for s in resultado.get("similares_rag", [])
    ]

    return VerificarDuplicidadResponse(
        proyecto_id=proyecto_id,
        nivel=resultado["nivel"],
        score_similitud=resultado["score_similitud"],
        proyecto_similar=resultado.get("proyecto_similar"),
        codigo_bpin=resultado.get("codigo_bpin"),
        estado_similar=resultado.get("estado_similar"),
        recomendacion=resultado["recomendacion"],
        puede_continuar=resultado["puede_continuar"],
        bloqueado=resultado.get("bloqueado", False),
        similares_rag=similares_rag,
    )


# ── M5: Evaluación Inversa (Modo 2) ───────────────────────────────────────────

async def evaluar_proyecto_service(
    *,
    texto_proyecto: str,
    plan_id: str | None,
    proyecto_id: str | None,
    db: AsyncSession,
    rag,
    http: httpx.AsyncClient,
    settings: Settings,
    guardar: bool = True,
    top_chunks_plan: int = 6,
) -> EvaluarProyectoResponse:
    """
    Modo 2 — Evaluación Inversa: diagnóstica un proyecto existente en 4 dimensiones.

    Flujo:
    1. Recupera chunks del Plan de Desarrollo vía RAG (si plan_id dado)
    2. Construye datos del municipio (desde ProyectoSGR si proyecto_id dado)
    3. Llama al agente_evaluador (RAG bidireccional + LLM)
    4. Mapea resultado a EvaluarProyectoResponse
    5. Persiste diagnostico_mga en ProyectoSGR si guardar=True
    """
    # ── 1. RAG: chunks del plan ────────────────────────────────────────────
    plan_chunks: list[str] = []
    if plan_id:
        try:
            resultados_rag = await rag.search(
                query=texto_proyecto[:400],
                limit=top_chunks_plan,
            )
            plan_chunks = [
                r.get("text", "") if isinstance(r, dict) else str(r)
                for r in resultados_rag if r
            ]
        except Exception as exc:
            logger.warning("[evaluar_proyecto_service] RAG search falló: %s", exc)

    # ── 2. Datos del municipio (desde proyecto si existe) ──────────────────
    datos_municipio: dict = {
        "divipola": None,
        "nombre_municipio": None,
        "categoria_municipio": None,
        "nbi": None,
        "icld": None,
    }

    proyecto_obj: ProyectoSGR | None = None
    if proyecto_id:
        result = await db.execute(select(ProyectoSGR).where(ProyectoSGR.id == proyecto_id))
        proyecto_obj = result.scalar_one_or_none()
        if proyecto_obj:
            datos_municipio["divipola"] = proyecto_obj.municipio_codigo
            datos_municipio["nombre_municipio"] = proyecto_obj.nombre

    # ── 3. Agente evaluador ────────────────────────────────────────────────
    resultado = await evaluar_proyecto(
        texto_proyecto=texto_proyecto,
        plan_chunks=plan_chunks,
        datos_municipio=datos_municipio,
        http=http,
        settings=settings,
    )

    # ── 4. Persistir diagnóstico ───────────────────────────────────────────
    if guardar and proyecto_obj:
        proyecto_obj.diagnostico_mga = {
            "score_total": resultado["score_total"],
            "cuadrante": resultado["cuadrante"],
            "semaforo": resultado["semaforo"],
            "en_plan": resultado["en_plan"],
            "estructura_mga": resultado["estructura_mga"]["score"],
            "alineacion_plan": resultado["alineacion_plan"]["score"],
            "analisis_estrategico": resultado["analisis_estrategico"]["score"],
            "calificacion_sgr": resultado["calificacion_sgr"]["score"],
        }
        proyecto_obj.en_plan = resultado["en_plan"]
        proyecto_obj.cuadrante = resultado["cuadrante"].lower().replace("_", "_")
        await db.commit()

    # ── 5. Construir response ──────────────────────────────────────────────
    def _dim(key: str) -> DiagnosticoDimension:
        d = resultado[key]
        return DiagnosticoDimension(
            nombre=d["nombre"],
            score=d["score"],
            nivel=d["nivel"],
            hallazgos=d.get("hallazgos", []),
            recomendaciones=d.get("recomendaciones", []),
        )

    return EvaluarProyectoResponse(
        estructura_mga=_dim("estructura_mga"),
        alineacion_plan=_dim("alineacion_plan"),
        analisis_estrategico=_dim("analisis_estrategico"),
        calificacion_sgr=_dim("calificacion_sgr"),
        score_total=resultado["score_total"],
        cuadrante=resultado["cuadrante"],
        cuadrante_label=resultado["cuadrante_label"],
        semaforo=resultado["semaforo"],
        semaforo_label=resultado["semaforo_label"],
        en_plan=resultado["en_plan"],
        evidencia_plan=resultado.get("evidencia_plan", ""),
        subflujo_inclusion=SubflujoInclusion(
            necesita_inclusion=resultado.get("necesita_inclusion_plan", False),
            checklist_concejo=resultado.get("checklist_concejo", []),
            texto_acuerdo_sugerido=resultado.get("acuerdo_concejo"),
        ),
        proyecto_id=proyecto_id,
        plan_id=plan_id,
    )
