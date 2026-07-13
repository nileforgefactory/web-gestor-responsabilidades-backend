"""Pipeline SGR — Modo 1: evaluar plan y generar candidatos de proyectos."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.slices.background_scraper.self_heal import asegurar_normas_en_rag
from app.slices.planes.models import Brecha, Plane
from app.slices.sgr.agents.agente_chat_mga import chat_editar_ficha
from app.slices.sgr.agents.agente_duplicidad import verificar_duplicidad
from app.slices.sgr.agents.agente_elegibilidad import evaluar_elegibilidad
from app.slices.sgr.agents.agente_evaluador import evaluar_proyecto
from app.slices.sgr.agents.agente_mga import generar_ficha_mga
from app.slices.sgr.models import FichaMGA, ProyectoSGR
from app.slices.sgr.schemas import (
    ActualizarFichaMGARequest,
    ChatFichaMGAResponse,
    ChatSesionesResponse,
    DiagnosticoDimension,
    EvaluarPlanResponse,
    EvaluarProyectoResponse,
    FichaMGAOut,
    ProyectoCandidatoResponse,
    SesionChatMeta,
    SesionChatOut,
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

    # ── 7. Persistir en DB (upsert por brecha_id — conserva id/ficha_mga) ──
    if guardar and top_candidatos:
        proyectos_existentes = await db.execute(
            select(ProyectoSGR).where(
                ProyectoSGR.plan_id == plan_id,
                ProyectoSGR.modo == "descubrimiento",
            )
        )
        existentes_por_brecha = {
            p.brecha_id: p for p in proyectos_existentes.scalars().all() if p.brecha_id is not None
        }
        brechas_nuevas = {c.brecha_id for c in top_candidatos}

        # Proyectos que ya tienen Ficha MGA: se protegen del barrido aunque el
        # usuario no los haya guardado explícitamente (así generar la ficha ya no
        # obliga a marcarlos como "guardados").
        ids_existentes = [p.id for p in existentes_por_brecha.values()]
        ficha_ids: set[str] = set()
        if ids_existentes:
            ficha_ids_result = await db.execute(
                select(FichaMGA.proyecto_id).where(FichaMGA.proyecto_id.in_(ids_existentes))
            )
            ficha_ids = set(ficha_ids_result.scalars().all())

        # Solo se borran los que ya no aparecen entre los nuevos candidatos,
        # que el usuario NUNCA guardó explícitamente y que no tienen Ficha MGA.
        for brecha_id, p in existentes_por_brecha.items():
            if brecha_id not in brechas_nuevas and p.guardado_en is None and p.id not in ficha_ids:
                await db.delete(p)

        for c in top_candidatos:
            brecha_obj = brechas_map.get(c.brecha_id)
            existente = existentes_por_brecha.get(c.brecha_id)

            campos = dict(
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
            )

            if existente is not None:
                # Actualiza scores/datos in-place: conserva id (y por tanto ficha_mga).
                for campo, valor in campos.items():
                    setattr(existente, campo, valor)
                c.id = existente.id
                c.guardado = existente.guardado_en is not None
                c.tiene_ficha_mga = existente.id in ficha_ids
            else:
                proyecto = ProyectoSGR(
                    id=str(uuid4()),
                    plan_id=plan_id,
                    brecha_id=c.brecha_id,
                    municipio_codigo=datos_municipio.get("divipola") or "00000000",
                    estado="borrador",
                    modo="descubrimiento",
                    **campos,
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

    # Nota: generar la Ficha MGA ya NO marca el proyecto como "guardado".
    # El guardado es explícito (botón "Guardar proyecto"); el proyecto con ficha
    # queda protegido del barrido de re-evaluación por su Ficha MGA (ver evaluar_plan_sgr).

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

    # ── 3b. Auto-sanado del RAG: trae normas citadas (brecha/proyecto) ─────
    await asegurar_normas_en_rag(
        [
            proyecto.nombre or "",
            proyecto.razon_elegibilidad or "",
            brecha_dict.get("referencia_legal", ""),
            brecha_dict.get("descripcion", ""),
            brecha_dict.get("recomendacion", ""),
        ],
        rag=rag,
        settings=settings,
    )

    # ── 4. Cargar el Plan (para filtrar el RAG y conocer el municipio real) ─
    plan_obj: Plane | None = None
    if proyecto.plan_id:
        plan_result = await db.execute(select(Plane).where(Plane.id == proyecto.plan_id))
        plan_obj = plan_result.scalar_one_or_none()

    # ── 4b. RAG: fragmentos del plan de desarrollo (filtrados a ESTE plan) ──
    # Sin filtrar por document_id/collection_id, una búsqueda global puede traer
    # chunks de OTRO plan/municipio indexado en la misma colección. Si el plan no
    # tiene ninguno de los dos identificadores, se omite la búsqueda (más seguro
    # que arriesgar mezclar contenido de otro municipio).
    plan_chunks: list[str] = []
    if plan_obj and (plan_obj.coleccion_id or plan_obj.qdrant_doc_id):
        query_text = (
            f"{proyecto.nombre} {proyecto.sector_sgr or ''} "
            f"{brecha_dict.get('titulo', '')} inversión pública"
        ).strip()
        try:
            resultados_rag = await rag.search(
                query=query_text,
                collection_ids=[plan_obj.coleccion_id] if plan_obj.coleccion_id else [],
                top_k=top_chunks_plan,
                score_threshold=settings.rag_default_score_threshold,
                document_id=plan_obj.qdrant_doc_id,
            )
            plan_chunks = [c.text for c in resultados_rag.chunks if c.text]
        except Exception as exc:
            logger.warning("[generar_ficha_mga] RAG search falló: %s", exc)

    # ── 5. Datos municipio: del PLAN (entidad real), no del proyecto ───────
    datos_municipio = {
        "divipola": proyecto.municipio_codigo,
        "nombre_municipio": (plan_obj.entidad if plan_obj else None) or proyecto.municipio_codigo,
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


# ── M4b: Edición manual y chat conversacional de la Ficha MGA ─────────────────

async def actualizar_ficha_mga_service(
    *,
    proyecto_id: str,
    payload: ActualizarFichaMGARequest,
    db: AsyncSession,
) -> FichaMGAOut:
    """
    Edición manual de la Ficha MGA: solo actualiza los campos no-None del payload.

    Recalcula campos_completos tras la actualización.
    """
    result = await db.execute(select(FichaMGA).where(FichaMGA.proyecto_id == proyecto_id))
    ficha = result.scalar_one_or_none()
    if ficha is None:
        raise ValueError(f"Ficha MGA para proyecto '{proyecto_id}' no encontrada")

    if payload.identificacion is not None:
        ficha.identificacion = payload.identificacion
    if payload.preparacion is not None:
        ficha.preparacion = payload.preparacion
    if payload.evaluacion is not None:
        ficha.evaluacion = payload.evaluacion
    if payload.programacion is not None:
        ficha.programacion = payload.programacion

    ficha.campos_completos = sum(
        1 for v in (ficha.identificacion, ficha.preparacion, ficha.evaluacion, ficha.programacion) if v
    )

    await db.commit()
    await db.refresh(ficha)
    logger.info(
        "[actualizar_ficha_mga] Proyecto %s → %d/4 secciones tras edición manual",
        proyecto_id,
        ficha.campos_completos,
    )
    return ficha_mga_to_out(ficha)


# ── Historial de chat por sesiones (hilos) ─────────────────────────────────────
#
# El historial se guarda dentro de la columna JSON `chat_historial` con la forma:
#   {"sesiones": [{"id","titulo","creada_en","mensajes":[{role,texto,timestamp}]}],
#    "activa": <id>}
# Retrocompatible: si en BD hay una lista plana (formato antiguo), se envuelve en
# una única sesión "Conversación inicial".


def _normalizar_sesiones(raw) -> dict:
    """Devuelve siempre la estructura {"sesiones": [...], "activa": id}."""
    if isinstance(raw, dict) and isinstance(raw.get("sesiones"), list):
        sesiones = raw["sesiones"]
        activa = raw.get("activa")
        if not activa and sesiones:
            activa = sesiones[-1]["id"]
        return {"sesiones": sesiones, "activa": activa}

    # Formato antiguo (lista plana) o vacío -> una sesión inicial.
    mensajes = raw if isinstance(raw, list) else []
    creada = (
        mensajes[0].get("timestamp")
        if mensajes and isinstance(mensajes[0], dict) and mensajes[0].get("timestamp")
        else datetime.utcnow().isoformat()
    )
    sid = uuid4().hex
    return {
        "sesiones": [
            {"id": sid, "titulo": "Conversación inicial", "creada_en": creada, "mensajes": mensajes}
        ],
        "activa": sid,
    }


def _sesion_por_id(estructura: dict, sesion_id: str | None) -> dict:
    """Sesión indicada o la activa; si no existe, la activa/última."""
    sesiones = estructura["sesiones"]
    if sesion_id:
        for s in sesiones:
            if s["id"] == sesion_id:
                return s
    activa = estructura.get("activa")
    for s in sesiones:
        if s["id"] == activa:
            return s
    return sesiones[-1]


def _meta_sesiones(estructura: dict) -> list[SesionChatMeta]:
    return [
        SesionChatMeta(
            id=s["id"],
            titulo=s.get("titulo") or "Conversación",
            creada_en=s.get("creada_en") or "",
            total_mensajes=len(s.get("mensajes") or []),
        )
        for s in estructura["sesiones"]
    ]


def ficha_mga_to_out(ficha: FichaMGA) -> FichaMGAOut:
    """Serializa una FichaMGA exponiendo la sesión de chat activa + metadatos."""
    estructura = _normalizar_sesiones(ficha.chat_historial)
    activa = _sesion_por_id(estructura, estructura.get("activa"))
    return FichaMGAOut(
        id=ficha.id,
        proyecto_id=ficha.proyecto_id,
        identificacion=ficha.identificacion,
        preparacion=ficha.preparacion,
        evaluacion=ficha.evaluacion,
        programacion=ficha.programacion,
        campos_completos=ficha.campos_completos,
        modelo_usado=ficha.modelo_usado,
        generado_en=ficha.generado_en,
        actualizado_en=ficha.actualizado_en,
        chat_historial=activa.get("mensajes") or [],
        chat_sesiones=_meta_sesiones(estructura),
        sesion_activa=activa["id"],
    )


async def _cargar_ficha(proyecto_id: str, db: AsyncSession) -> FichaMGA:
    result = await db.execute(select(FichaMGA).where(FichaMGA.proyecto_id == proyecto_id))
    ficha = result.scalar_one_or_none()
    if ficha is None:
        raise ValueError(f"Ficha MGA para proyecto '{proyecto_id}' no encontrada")
    return ficha


async def listar_sesiones_chat_service(*, proyecto_id: str, db: AsyncSession) -> ChatSesionesResponse:
    """Lista todas las sesiones (hilos) de chat con sus mensajes."""
    ficha = await _cargar_ficha(proyecto_id, db)
    estructura = _normalizar_sesiones(ficha.chat_historial)
    return ChatSesionesResponse(
        sesiones=[SesionChatOut(**s) for s in estructura["sesiones"]],
        activa=estructura.get("activa"),
    )


async def crear_sesion_chat_service(*, proyecto_id: str, db: AsyncSession) -> ChatSesionesResponse:
    """Crea una nueva sesión (hilo) vacía y la deja como activa."""
    ficha = await _cargar_ficha(proyecto_id, db)
    estructura = _normalizar_sesiones(ficha.chat_historial)
    numero = len(estructura["sesiones"]) + 1
    nueva = {
        "id": uuid4().hex,
        "titulo": f"Conversación {numero}",
        "creada_en": datetime.utcnow().isoformat(),
        "mensajes": [],
    }
    estructura["sesiones"].append(nueva)
    estructura["activa"] = nueva["id"]
    ficha.chat_historial = estructura
    await db.commit()
    await db.refresh(ficha)
    estructura = _normalizar_sesiones(ficha.chat_historial)
    return ChatSesionesResponse(
        sesiones=[SesionChatOut(**s) for s in estructura["sesiones"]],
        activa=estructura.get("activa"),
    )


async def chat_ficha_mga_service(
    *,
    proyecto_id: str,
    mensaje: str,
    db: AsyncSession,
    rag,
    http: httpx.AsyncClient,
    settings: Settings,
    sesion_id: str | None = None,
) -> ChatFichaMGAResponse:
    """
    Chat de edición conversacional sobre la Ficha MGA.

    Llama al agente_chat_mga, aplica los cambios devueltos a la ficha y persiste
    el turno de usuario y el de asistente en chat_historial.
    """
    result = await db.execute(select(FichaMGA).where(FichaMGA.proyecto_id == proyecto_id))
    ficha = result.scalar_one_or_none()
    if ficha is None:
        raise ValueError(f"Ficha MGA para proyecto '{proyecto_id}' no encontrada")

    # Auto-sanado del RAG: si el usuario cita una norma que falta, se trae antes
    # de que el agente edite la ficha.
    await asegurar_normas_en_rag([mensaje], rag=rag, settings=settings)

    ficha_actual = {
        "identificacion": ficha.identificacion,
        "preparacion": ficha.preparacion,
        "evaluacion": ficha.evaluacion,
        "programacion": ficha.programacion,
    }

    # Sesión (hilo) objetivo: la indicada o la activa. El agente solo ve el
    # historial de ESA sesión (contexto aislado por hilo).
    estructura = _normalizar_sesiones(ficha.chat_historial)
    sesion = _sesion_por_id(estructura, sesion_id)
    historial = list(sesion.get("mensajes") or [])

    resultado = await chat_editar_ficha(
        ficha_actual=ficha_actual,
        mensaje_usuario=mensaje,
        historial=historial,
        http=http,
        settings=settings,
    )

    cambios = resultado.get("cambios", {})
    if "identificacion" in cambios:
        ficha.identificacion = cambios["identificacion"]
    if "preparacion" in cambios:
        ficha.preparacion = cambios["preparacion"]
    if "evaluacion" in cambios:
        ficha.evaluacion = cambios["evaluacion"]
    if "programacion" in cambios:
        ficha.programacion = cambios["programacion"]

    ficha.campos_completos = sum(
        1 for v in (ficha.identificacion, ficha.preparacion, ficha.evaluacion, ficha.programacion) if v
    )

    # Autotítulo: si la sesión aún no tiene mensajes, usa un extracto del primero.
    if not sesion.get("mensajes"):
        sesion["titulo"] = mensaje.strip()[:48] + ("…" if len(mensaje.strip()) > 48 else "")

    sesion["mensajes"] = historial + [
        {"role": "usuario", "texto": mensaje, "timestamp": datetime.utcnow().isoformat()},
        {
            "role": "asistente",
            "texto": resultado["respuesta_ia"],
            "timestamp": datetime.utcnow().isoformat(),
        },
    ]
    estructura["activa"] = sesion["id"]

    # chat_historial es una columna JSON — reasignar la estructura completa para
    # que SQLAlchemy detecte el cambio (no trackea mutación in-place por defecto).
    ficha.chat_historial = estructura

    await db.commit()
    await db.refresh(ficha)
    logger.info(
        "[chat_ficha_mga] Proyecto %s → %d/4 secciones, %d cambios aplicados (sesión %s)",
        proyecto_id,
        ficha.campos_completos,
        len(cambios),
        sesion["id"],
    )
    return ChatFichaMGAResponse(
        respuesta_ia=resultado["respuesta_ia"],
        ficha=ficha_mga_to_out(ficha),
    )


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

    # ── 2b. Nombre del municipio: viene del plan asociado, no del nombre del
    # proyecto (bug anterior usaba proyecto.nombre como si fuera el municipio).
    nombre_municipio = None
    if proyecto.plan_id:
        plan_result = await db.execute(select(Plane).where(Plane.id == proyecto.plan_id))
        plan_obj = plan_result.scalar_one_or_none()
        if plan_obj:
            nombre_municipio = plan_obj.entidad

    datos_municipio = {
        "divipola": proyecto.municipio_codigo,
        "nombre_municipio": nombre_municipio,
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
    # ── 0. Auto-sanado del RAG: trae normas citadas en el texto que falten ──
    await asegurar_normas_en_rag([texto_proyecto], rag=rag, settings=settings)

    # ── 1. Cargar el Plan (para filtrar el RAG y conocer el municipio real) ─
    plan_obj: Plane | None = None
    if plan_id:
        plan_result = await db.execute(select(Plane).where(Plane.id == plan_id))
        plan_obj = plan_result.scalar_one_or_none()

    # ── 1b. RAG: chunks del plan (filtrados a ESTE plan) ───────────────────
    # Sin filtrar por document_id/collection_id, una búsqueda global puede traer
    # chunks de OTRO plan/municipio indexado en la misma colección. Si el plan no
    # tiene ninguno de los dos identificadores, se omite la búsqueda (más seguro
    # que arriesgar mezclar contenido de otro municipio).
    plan_chunks: list[str] = []
    if plan_obj and (plan_obj.coleccion_id or plan_obj.qdrant_doc_id):
        try:
            resultados_rag = await rag.search(
                query=texto_proyecto[:400],
                collection_ids=[plan_obj.coleccion_id] if plan_obj.coleccion_id else [],
                top_k=top_chunks_plan,
                score_threshold=settings.rag_default_score_threshold,
                document_id=plan_obj.qdrant_doc_id,
            )
            plan_chunks = [c.text for c in resultados_rag.chunks if c.text]
        except Exception as exc:
            logger.warning("[evaluar_proyecto_service] RAG search falló: %s", exc)

    # ── 2. Datos del municipio: del PLAN (entidad real) y/o del proyecto ───
    datos_municipio: dict = {
        "divipola": None,
        "nombre_municipio": plan_obj.entidad if plan_obj else None,
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
            if not datos_municipio["nombre_municipio"]:
                datos_municipio["nombre_municipio"] = proyecto_obj.municipio_codigo

    # ── 3. Agente evaluador ────────────────────────────────────────────────
    resultado = await evaluar_proyecto(
        texto_proyecto=texto_proyecto,
        plan_chunks=plan_chunks,
        datos_municipio=datos_municipio,
        http=http,
        settings=settings,
    )

    # ── 4. Crear proyecto si no existe (evaluación en frío con plan_id) ────
    if guardar and proyecto_obj is None and plan_id:
        proyecto_obj = ProyectoSGR(
            plan_id=plan_id,
            municipio_codigo=datos_municipio.get("divipola") or "00000000",
            nombre=texto_proyecto[:120],
            sector_sgr="sin_clasificar",
            estado="borrador",
            modo="evaluacion_inversa",
        )
        db.add(proyecto_obj)
        await db.flush()
    # Si no hay plan_id ni proyecto_id, no hay FK válida para persistir: se omite guardado.

    # ── 5. Persistir diagnóstico ───────────────────────────────────────────
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

    # ── 6. Construir response ──────────────────────────────────────────────
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
        proyecto_id=(proyecto_obj.id if proyecto_obj else proyecto_id),
        plan_id=plan_id,
    )


# ── M6: Guardado explícito de proyecto ─────────────────────────────────────────

async def guardar_proyecto_service(*, proyecto_id: str, db: AsyncSession) -> ProyectoSGR:
    """Marca un ProyectoSGR como guardado explícitamente por el usuario.

    Protege al proyecto del barrido de re-evaluación de evaluar_plan_sgr (Modo 1)
    y le da feedback claro al usuario en Modo 2 (antes el guardado era implícito
    y silencioso).
    """
    result = await db.execute(select(ProyectoSGR).where(ProyectoSGR.id == proyecto_id))
    proyecto = result.scalar_one_or_none()
    if proyecto is None:
        raise ValueError(f"Proyecto '{proyecto_id}' no encontrado")

    if proyecto.guardado_en is None:
        proyecto.guardado_en = datetime.utcnow()
        await db.commit()
        await db.refresh(proyecto)

    return proyecto


async def eliminar_proyecto_service(*, proyecto_id: str, db: AsyncSession) -> None:
    """Elimina un ProyectoSGR y su Ficha MGA asociada (cascade por FK)."""
    result = await db.execute(select(ProyectoSGR).where(ProyectoSGR.id == proyecto_id))
    proyecto = result.scalar_one_or_none()
    if proyecto is None:
        raise ValueError(f"Proyecto '{proyecto_id}' no encontrado")

    await db.delete(proyecto)
    await db.commit()
