"""
Servicio principal de análisis agentico.
Implementa el loop coordinador + persistencia + SSE con heartbeat.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.session_store import SessionStore, get_session_store
from app.slices.analysis.agents import (
    actores_agent,
    brechas_agent,
    leyes_agent,
    matriz_agent,
    responsabilidades_agent,
    run_parallel_agents,
    search_multi_query,
)
from app.slices.analysis.coordinator import coordinator_decide
from app.slices.analysis.schemas import AnalyzePlanRequest
from app.slices.planes import repository as planes_repo
from app.slices.planes.schemas import (
    ActorIn,
    BrechaIn,
    MatrizIn,
    NormaIn,
    PlanUpdate,
    ResponsabilidadIn,
)
from app.slices.rag.service import RagService

logger = logging.getLogger(__name__)


# ── SSE helpers ────────────────────────────────────────────────────────────

async def _stream_with_heartbeat(queue: asyncio.Queue) -> AsyncIterator[str]:
    """Genera eventos SSE con heartbeat cada 20s para mantener la conexión."""
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=20.0)
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if event.get("type") in ("done", "error"):
                break
        except asyncio.TimeoutError:
            yield 'data: {"type":"heartbeat"}\n\n'


# ── Persistencia ───────────────────────────────────────────────────────────

async def _persist_results(
    db: AsyncSession,
    plan_id: str,
    context: dict[str, Any],
) -> None:
    """Persiste los resultados del análisis en MySQL."""
    responsabilidades = [
        ResponsabilidadIn(
            titulo=r["titulo"][:500],
            descripcion=r.get("descripcion") or None,
            sector=r.get("sector") or None,
            tipo=r.get("tipo", "P"),
            referencia_legal=r.get("referencia_legal") or None,
        )
        for r in context.get("responsabilidades", [])
        if r.get("titulo")
    ]

    brechas = [
        BrechaIn(
            titulo=b["titulo"][:500],
            descripcion=b.get("descripcion") or None,
            tipo=b.get("tipo", "critica"),
            severidad=b.get("severidad", "alta"),
            referencia_legal=b.get("referencia_legal") or None,
        )
        for b in context.get("brechas", [])
        if b.get("titulo")
    ]

    normas = [
        NormaIn(
            norma_codigo=n.get("norma_codigo") or None,
            titulo=(n.get("titulo") or n.get("norma_codigo", "Norma"))[:500],
            articulos=n.get("articulos") or None,
            extracto=n.get("extracto") or None,
            tipo=n.get("tipo", "ley"),
            vigente=n.get("vigente", True),
        )
        for n in context.get("leyes", [])
        if n.get("titulo") or n.get("norma_codigo")
    ]

    actores = [
        ActorIn(
            nombre=a["nombre"][:300],
            tipo=a.get("tipo", "otro"),
        )
        for a in context.get("actores", [])
        if a.get("nombre")
    ]

    matriz = [
        MatrizIn(
            competencia=m["competencia"][:300],
            ley_base=m.get("ley_base") or None,
            nacion=m.get("nacion", "N"),
            departamento=m.get("departamento", "N"),
            municipio=m.get("municipio", "N"),
            especializado=m.get("especializado", "N"),
            brecha=m.get("brecha", "ok") if m.get("brecha") in ("ok", "critica", "duplicidad", "indefinido") else "ok",
        )
        for m in context.get("matriz", [])
        if m.get("competencia")
    ]

    # Actualizar totales y sub-entidades en el plan
    update = PlanUpdate(
        estado="analizado",
        resp_total=len(responsabilidades),
        leyes_total=len(normas),
        actores_total=len(actores),
        brechas_total=len(brechas),
        avance_pct=_calc_avance(context),
    )

    plane = await planes_repo.get_plane(db, plan_id)
    if plane is None:
        logger.error("Plan '%s' no encontrado para persistir resultados", plan_id)
        return

    await planes_repo.update_plane(db, plan_id, update)

    # Reemplazar sub-entidades: borrar las existentes y crear nuevas
    await planes_repo.replace_sub_entities(
        db, plan_id,
        responsabilidades=responsabilidades,
        brechas=brechas,
        normas=normas,
        actores=actores,
        matriz=matriz,
    )


def _calc_avance(context: dict[str, Any]) -> float:
    """Calcula % de avance basado en brechas vs responsabilidades."""
    total = len(context.get("responsabilidades", []))
    if not total:
        return 0.0
    brechas_criticas = sum(
        1 for b in context.get("brechas", [])
        if b.get("severidad") == "alta"
    )
    return round(max(0.0, (1 - brechas_criticas / total) * 100), 2)


# ── Pipeline principal ─────────────────────────────────────────────────────

async def analyze_plan_stream(
    request: AnalyzePlanRequest,
    rag: RagService,
    db: AsyncSession,
) -> tuple[AsyncIterator[str], str | None]:
    """
    Inicia el pipeline de análisis agentico.
    Retorna (generador_SSE, session_id).
    """
    settings = get_settings()
    queue: asyncio.Queue = asyncio.Queue()
    store: SessionStore | None = get_session_store()

    session_id: str | None = None
    if store:
        session_id = await store.create_session(
            plan_id=request.plan_id,
            meta={"nivel": request.nivel, "depth": request.depth},
        )

    async def _emit(event: dict) -> None:
        await queue.put(event)
        if store and session_id:
            try:
                await store.append_event(session_id, event)
            except Exception as exc:
                logger.warning("Error guardando evento en Redis: %s", exc)

    async def pipeline() -> None:
        t_start = time.monotonic()
        context: dict[str, Any] = {
            "responsabilidades": [],
            "leyes": [],
            "actores": [],
            "brechas": [],
            "extra_chunks": [],
            "matriz": [],
        }

        try:
            # ── Análisis inicial paralelo ──────────────────────────────
            await _emit({"type": "log", "msg": "Iniciando análisis inicial con agentes especializados..."})

            initial_agents = [
                ("responsabilidades", lambda: responsabilidades_agent(
                    rag, request.collection_id, request.nivel, request.depth
                )),
                ("leyes", lambda: leyes_agent(
                    rag, request.collection_id, request.nivel, request.depth
                )),
                ("actores", lambda: actores_agent(
                    rag, request.collection_id, request.nivel, request.depth
                )),
            ]
            if request.depth == "profundo":
                initial_agents.append(("brechas", lambda: brechas_agent(
                    rag, request.collection_id, request.nivel, request.depth
                )))

            initial_results = await run_parallel_agents(initial_agents, _emit)
            context.update(initial_results)

            # ── Loop agentico ─────────────────────────────────────────
            max_iter = settings.analysis_max_iterations

            for iteration in range(1, max_iter + 1):
                if request.depth == "basico":
                    break

                await _emit({
                    "type": "log",
                    "msg": f"Evaluando completitud (iteración {iteration}/{max_iter})...",
                })

                decision = await coordinator_decide(
                    rag=rag,
                    context=context,
                    nivel=request.nivel,
                    sectores=request.sectores,
                    profundidad=request.depth,
                    iteration=iteration,
                    max_iterations=max_iter,
                )

                await _emit({
                    "type": "coordinator_decision",
                    "accion": decision["accion"],
                    "razon": decision.get("razon", ""),
                    "confianza": decision.get("confianza", 1.0),
                })

                if decision["accion"] == "finalizar":
                    await _emit({
                        "type": "log",
                        "msg": f"Análisis completo con confianza {decision.get('confianza', 1.0):.0%}",
                    })
                    break

                elif decision["accion"] == "buscar_mas":
                    query = decision.get("query", "responsabilidades territoriales")
                    await _emit({"type": "log", "msg": f"Buscando contexto adicional: '{query}'"})
                    new_chunks = await search_multi_query(
                        rag, [query], request.collection_id, top_k_per_query=5
                    )
                    context["extra_chunks"].extend(new_chunks)

                    new_results = await run_parallel_agents([
                        ("responsabilidades", lambda nc=new_chunks: responsabilidades_agent(
                            rag, request.collection_id, request.nivel, request.depth, extra_chunks=nc
                        )),
                        ("leyes", lambda nc=new_chunks: leyes_agent(
                            rag, request.collection_id, request.nivel, request.depth, extra_chunks=nc
                        )),
                    ], _emit)

                    for agent_name, new_items in new_results.items():
                        existing_titles = {r.get("titulo") for r in context.get(agent_name, [])}
                        context[agent_name] += [
                            r for r in (new_items or [])
                            if r.get("titulo") not in existing_titles
                        ]

                elif decision["accion"] == "reanalizar_sector":
                    sector = decision.get("sector", "")
                    if not sector:
                        continue
                    await _emit({"type": "log", "msg": f"Profundizando en sector: {sector}"})
                    sector_chunks = await search_multi_query(
                        rag,
                        [f"responsabilidades {sector} municipal", f"ley norma {sector} colombia"],
                        request.collection_id,
                    )
                    sector_resp = await responsabilidades_agent(
                        rag, request.collection_id, request.nivel, request.depth,
                        extra_chunks=sector_chunks,
                    )
                    existing_titles = {r.get("titulo") for r in context["responsabilidades"]}
                    context["responsabilidades"] += [
                        r for r in (sector_resp or [])
                        if r.get("titulo") not in existing_titles
                    ]

            # ── Brechas (estandar/profundo si no se corrió antes) ──────
            if request.depth in ("estandar", "profundo") and not context.get("brechas"):
                await _emit({"type": "agent_start", "agent": "brechas"})
                context["brechas"] = await brechas_agent(
                    rag, request.collection_id, request.nivel, request.depth
                )
                await _emit({
                    "type": "agent_done", "agent": "brechas",
                    "count": len(context["brechas"]),
                })

            # ── Consolidación: Matriz ──────────────────────────────────
            if request.depth in ("estandar", "profundo"):
                await _emit({"type": "agent_start", "agent": "matriz"})
                context["matriz"] = await matriz_agent(rag, request.collection_id, context)
                await _emit({
                    "type": "agent_done", "agent": "matriz",
                    "count": len(context["matriz"]),
                })

            # ── Persistencia ───────────────────────────────────────────
            await _emit({"type": "saving", "msg": "Guardando resultados en base de datos..."})
            await _persist_results(db, request.plan_id, context)

            elapsed = round(time.monotonic() - t_start, 1)
            if store and session_id:
                await store.mark_done(session_id)

            await _emit({
                "type": "done",
                "plan_id": request.plan_id,
                "session_id": session_id,
                "msg": f"Análisis completado en {elapsed}s",
                "data": {
                    "responsabilidades": len(context["responsabilidades"]),
                    "leyes": len(context["leyes"]),
                    "actores": len(context["actores"]),
                    "brechas": len(context["brechas"]),
                    "matriz": len(context["matriz"]),
                },
            })

        except Exception as exc:
            logger.exception("Error fatal en pipeline de análisis")
            await _emit({"type": "error", "error": str(exc), "session_id": session_id})

    asyncio.create_task(pipeline())
    return _stream_with_heartbeat(queue), session_id
