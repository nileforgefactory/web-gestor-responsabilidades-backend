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
        agents = ["responsabilidades", "leyes", "actores"]
        if profundidad == "profundo":
            agents.append("brechas")

        async def one(name: str) -> None:
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
                    extra_query=extra_query,
                    plan_excerpt=plan_excerpt,
                )
                merge_key = "codigo" if name == "leyes" else "titulo"
                _merge_unique(context[name], rows, key=merge_key)
                await emit({"type": "agent_done", "agent": name, "count": len(context[name])})
            except Exception as exc:
                logger.exception("Agente %s falló", name)
                await emit({"type": "agent_error", "agent": name, "error": str(exc)})

        await asyncio.gather(*(one(a) for a in agents))

    await emit({"type": "log", "msg": "Ejecutando agentes iniciales..."})
    await run_agents_batch()

    iteraciones = 0
    max_iter = settings.analysis_max_iterations if profundidad != "basico" else 0

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
    """
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def emit(event: dict[str, Any]) -> None:
        await queue.put(event)

    async def worker() -> None:
        try:
            await run_document_analysis(emit=emit, **kwargs)
        except Exception as exc:
            logger.exception("Pipeline análisis falló")
            await queue.put({"type": "error", "error": str(exc)})
        finally:
            await queue.put(None)

    task = asyncio.create_task(worker())

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
    finally:
        if not task.done():
            task.cancel()
