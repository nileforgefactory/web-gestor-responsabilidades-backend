"""Pipeline de análisis: OCR → indexación → agentes → coordinador → matriz."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.slices.analysis.agents import run_agent, run_matriz_agent
from app.slices.analysis.coordinator import coordinator_decide
from app.slices.analysis.persist import persist_analysis
from app.slices.analysis.schemas import AnalisisDocumentoResponse
from app.slices.rag.extract import (
    derive_document_id_from_filename,
    extract_document_from_bytes,
)
from app.slices.rag.service import RagService

logger = logging.getLogger(__name__)

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]

# Registro de tareas SSE activas: session_id → asyncio.Task
_active_tasks: dict[str, asyncio.Task[None]] = {}


def cancel_analysis(session_id: str) -> bool:
    """Cancela la tarea de análisis asociada al session_id. Retorna True si existía."""
    task = _active_tasks.pop(session_id, None)
    if task and not task.done():
        task.cancel()
        return True
    return False


async def _noop_emit(_: dict[str, Any]) -> None:
    """Emisor vacío cuando no se requiere SSE."""
    pass


def _merge_unique(items: list[dict], new_items: list[dict], key: str = "titulo") -> None:
    """Añade ítems evitando duplicados por clave (titulo o codigo)."""
    seen = {str(i.get(key, "")).lower() for i in items}
    for row in new_items:
        k = str(row.get(key, "")).lower()
        if k and k not in seen:
            items.append(row)
            seen.add(k)


async def run_document_analysis(
    *,
    rag: RagService,
    settings: Settings,
    raw: bytes,
    filename: str,
    collection_id: str,
    normativa_collection_ids: list[str],
    nivel: str,
    profundidad: str,
    entidad: str,
    plan_id: str | None,
    titulo_plan: str | None,
    guardar_mysql: bool,
    db: AsyncSession | None,
    emit: EmitFn = _noop_emit,
    max_iteraciones: int | None = None,
) -> AnalisisDocumentoResponse:
    """
    Ejecuta el pipeline completo de análisis de un plan de desarrollo.

    Orden: extracción → indexación Qdrant → agentes → coordinador → matriz → MySQL opcional.

    Args:
        emit: Callback async para eventos SSE (log, agent_done, etc.).
    """
    await rag.ensure_collection()

    await emit({"type": "log", "msg": "Extrayendo texto (OCR si aplica)..."})
    extraccion = await extract_document_from_bytes(raw, filename, settings=settings)

    doc_id = derive_document_id_from_filename(filename)
    all_collections = list(dict.fromkeys([collection_id, *normativa_collection_ids]))

    await emit({"type": "log", "msg": "Indexando plan en Qdrant..."})
    ingesta = await rag.ingest_text(
        collection_id=collection_id,
        document_id=doc_id,
        content=extraccion.text,
        chunk_size=700,
        chunk_overlap=120,
        title=titulo_plan or doc_id,
        source_filename=filename,
        chunk_strategy=settings.default_chunk_strategy,
        extraction_method=extraccion.extraction_method.value,
    )

    await emit(
        {
            "type": "indexing_done",
            "msg": f"{ingesta.chunks_indexed} chunks indexados",
            "chunks": ingesta.chunks_indexed,
        }
    )

    context: dict[str, Any] = {
        "responsabilidades": [],
        "leyes": [],
        "actores": [],
        "brechas": [],
    }
    plan_excerpt = extraccion.text[:12_000]
    http = rag.http

    async def run_agents_batch(extra_query: str | None = None) -> None:
        base_agents = ["responsabilidades", "leyes", "actores"]

        async def one(name: str, extra: str | None = extra_query) -> None:
            await emit({"type": "agent_start", "agent": name})
            try:
                rows = await run_agent(
                    rag=rag,
                    http=http,
                    settings=settings,
                    agent=name,
                    collection_ids=all_collections,
                    nivel=nivel,
                    profundidad=profundidad,
                    entidad=entidad,
                    extra_query=extra,
                    plan_excerpt=plan_excerpt,
                )
                merge_key = {"leyes": "codigo", "actores": "nombre"}.get(name, "titulo")
                _merge_unique(context[name], rows, key=merge_key)
                await emit({"type": "agent_done", "agent": name, "count": len(context[name])})
            except Exception as exc:
                logger.exception("Agente %s falló", name)
                await emit({"type": "agent_error", "agent": name, "error": str(exc)})

        await asyncio.gather(*(one(a) for a in base_agents))

        # Brechas: se ejecuta DESPUÉS de los demás para poder cruzar información
        if profundidad == "profundo":
            # Construye un resumen del contexto extraído para inyectar al agente de brechas
            resp_lines = "\n".join(
                f"- {r.get('titulo','')} [{r.get('tipo','P')}] sector={r.get('sector','')} ley={r.get('referencia_legal','')}"
                for r in context["responsabilidades"][:30]
            )
            actor_lines = "\n".join(
                f"- {a.get('nombre','')} nivel={a.get('nivel','')} tipo={a.get('tipo','')}"
                for a in context["actores"][:20]
            )
            ley_lines = "\n".join(
                f"- {l.get('codigo','')} | {l.get('titulo','')}"
                for l in context["leyes"][:20]
            )
            cross_query = (
                f"Responsabilidades identificadas en el plan:\n{resp_lines or 'Ninguna'}\n\n"
                f"Actores identificados:\n{actor_lines or 'Ninguno'}\n\n"
                f"Normas identificadas:\n{ley_lines or 'Ninguna'}\n\n"
                f"Identifica qué obligaciones legales NO están cubiertas por los actores listados."
            )
            await one("brechas", extra=cross_query)

    await emit({"type": "log", "msg": "Ejecutando agentes iniciales..."})
    await run_agents_batch()

    iteraciones = 0
    max_iter = 0 if profundidad == "basico" else (
        max_iteraciones if max_iteraciones is not None else settings.analysis_max_iterations
    )

    for iteration in range(1, max_iter + 1):
        iteraciones = iteration
        await emit({"type": "log", "msg": f"Coordinador iteración {iteration}/{max_iter}..."})
        decision = await coordinator_decide(
            http=http,
            settings=settings,
            context=context,
            nivel=nivel,
            profundidad=profundidad,
            iteration=iteration,
            max_iterations=max_iter,
        )
        await emit(
            {
                "type": "coordinator_decision",
                "accion": decision.get("accion"),
                "razon": decision.get("razon"),
                "confianza": decision.get("confianza"),
            }
        )
        accion = decision.get("accion", "finalizar")
        if accion == "finalizar":
            break
        if accion == "buscar_mas":
            await run_agents_batch(extra_query=str(decision.get("query", "")))
        elif accion == "reanalizar_sector":
            sector = str(decision.get("sector", ""))
            await run_agents_batch(extra_query=f"responsabilidades sector {sector}")

    matriz: list[dict[str, Any]] = []
    if profundidad in ("estandar", "profundo"):
        await emit({"type": "agent_start", "agent": "matriz"})
        try:
            matriz = await run_matriz_agent(
                http=http,
                settings=settings,
                context=context,
                nivel=nivel,
                profundidad=profundidad,
            )
            await emit({"type": "agent_done", "agent": "matriz", "count": len(matriz)})
        except Exception as exc:
            await emit({"type": "agent_error", "agent": "matriz", "error": str(exc)})

    context["matriz"] = matriz

    # ── Síntesis ejecutiva del análisis ──────────────────────────────────────
    def _build_sintesis(ctx: dict[str, Any], nivel_plan: str) -> str:
        resp_n  = len(ctx.get("responsabilidades", []))
        leyes_n = len(ctx.get("leyes", []))
        act_n   = len(ctx.get("actores", []))
        bre_n   = len(ctx.get("brechas", []))
        mat_n   = len(ctx.get("matriz", []))

        criticas = [b for b in ctx.get("brechas", []) if b.get("tipo") in ("critica", "sin_responsable")]
        dups     = [b for b in ctx.get("brechas", []) if b.get("tipo") == "duplicidad"]

        sectores = list({r.get("sector", "") for r in ctx.get("responsabilidades", []) if r.get("sector")})

        partes = [
            f"Plan de nivel {nivel_plan} analizado con {resp_n} responsabilidades identificadas, "
            f"{leyes_n} normas aplicables y {act_n} actores institucionales.",
        ]
        if mat_n:
            partes.append(f"La matriz de competencias contiene {mat_n} entradas.")
        if criticas:
            partes.append(
                f"Se detectaron {len(criticas)} brecha(s) crítica(s): "
                + "; ".join(b.get("titulo", "sin título") for b in criticas[:3])
                + ("..." if len(criticas) > 3 else ".")
            )
        if dups:
            partes.append(f"Se identificaron {len(dups)} duplicidad(es) de competencias entre niveles territoriales.")
        if sectores:
            partes.append(f"Sectores cubiertos: {', '.join(sectores[:6])}{'...' if len(sectores) > 6 else ''}.")
        if bre_n == 0:
            partes.append("No se registraron brechas relevantes en el análisis.")

        return " ".join(partes)

    sintesis = _build_sintesis(context, nivel)

    guardado = False
    final_plan_id = plan_id

    if guardar_mysql and db is not None:
        await emit({"type": "saving", "msg": "Guardando en MySQL..."})
        final_plan_id = await persist_analysis(
            db,
            plan_id=plan_id,
            titulo=titulo_plan or doc_id,
            nivel=nivel,
            archivo_nombre=filename,
            qdrant_doc_id=doc_id,
            result=context,
            descripcion=sintesis,
        )
        guardado = True

    response = AnalisisDocumentoResponse(
        plan_id=final_plan_id,
        document_id=doc_id,
        collection_id=collection_id,
        metodo_extraccion=extraccion.extraction_method.value,
        caracteres_extraidos=extraccion.char_count,
        chunks_indexados=ingesta.chunks_indexed,
        chunk_strategy=ingesta.chunk_strategy,
        chunk_profile=ingesta.chunk_profile,
        responsabilidades=context["responsabilidades"],
        leyes=context["leyes"],
        actores=context["actores"],
        brechas=context["brechas"],
        matriz=matriz,
        iteraciones_coordinador=iteraciones,
        guardado_en_mysql=guardado,
    )
    session_id = str(uuid.uuid4())
    await emit({"type": "done", "plan_id": final_plan_id, "session_id": session_id, "result": response.model_dump()})
    return response


async def stream_document_analysis(
    **kwargs: Any,
) -> AsyncIterator[str]:
    """
    Envuelve ``run_document_analysis`` y emite líneas SSE (data: JSON).

    Incluye heartbeat cada ~20s si no hay eventos.
    Emite ``session_started`` como primer evento para que el cliente
    pueda llamar al endpoint de cancelación.
    """
    session_id = str(uuid.uuid4())
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def emit(event: dict[str, Any]) -> None:
        await queue.put(event)

    async def worker() -> None:
        try:
            await run_document_analysis(emit=emit, **kwargs)
        except asyncio.CancelledError:
            await queue.put({"type": "cancelled", "msg": "Análisis detenido por el usuario"})
        except Exception as exc:
            logger.exception("Pipeline análisis falló")
            await queue.put({"type": "error", "error": str(exc)})
        finally:
            _active_tasks.pop(session_id, None)
            await queue.put(None)

    task = asyncio.create_task(worker())
    _active_tasks[session_id] = task

    # Primer evento: expone el session_id al cliente para permitir cancelación
    yield f"data: {json.dumps({'type': 'session_started', 'session_id': session_id}, ensure_ascii=False)}\n\n"

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=20.0)
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'heartbeat'}, ensure_ascii=False)}\n\n"
                continue
            if event is None:
                break
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        # Chunk final explícito: garantiza que el cliente reciba el cierre correcto
        yield "data: \n\n"
    finally:
        if not task.done():
            task.cancel()
        _active_tasks.pop(session_id, None)
