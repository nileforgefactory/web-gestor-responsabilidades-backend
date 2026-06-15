"""Pipeline de análisis: OCR → indexación → agentes → coordinador → matriz."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
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
from app.slices.scraper.service import ScraperService

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


async def _await_con_progreso(coro: Awaitable[Any], *, emit: EmitFn, msg: str, intervalo: float = 10.0) -> Any:
    """
    Espera una corrutina larga (OCR, indexación) emitiendo un evento de progreso
    cada ``intervalo`` segundos para mantener viva la conexión SSE y evitar que la
    petición se corte por inactividad. El trabajo pesado corre fuera del event loop
    (asyncio.to_thread), por lo que el loop queda libre para emitir.
    """
    task: asyncio.Task[Any] = asyncio.ensure_future(coro)
    t0 = time.monotonic()
    while not task.done():
        done, _ = await asyncio.wait({task}, timeout=intervalo)
        if not done:
            await emit({"type": "log", "msg": f"{msg}… ({int(time.monotonic() - t0)}s)"})
    return task.result()


def _merge_unique(items: list[dict], new_items: list[dict], key: str = "titulo") -> None:
    """Añade ítems evitando duplicados por clave (titulo o codigo)."""
    seen = {str(i.get(key, "")).lower() for i in items}
    for row in new_items:
        k = str(row.get(key, "")).lower()
        if k and k not in seen:
            items.append(row)
            seen.add(k)


def _cobertura_metrics(context: dict[str, Any]) -> dict[str, Any]:
    """
    Confianza OBJETIVA del análisis (0-1), calculada sobre señales medibles del
    contexto extraído — NO auto-reportada por el LLM. Da soporte real al corte
    de iteraciones del coordinador.

    Señales y pesos:
      · presencia  (0.35): que existan responsabilidades, leyes y actores (3/3).
      · vínculo    (0.25): % de responsabilidades con norma relacional (id_norma_ref).
      · rag        (0.20): score RAG promedio de las responsabilidades (similitud de chunks).
      · sectorial  (0.20): nº de sectores distintos cubiertos (≥5 = completo).
    """
    resp    = context.get("responsabilidades", []) or []
    leyes   = context.get("leyes", []) or []
    actores = context.get("actores", []) or []

    n_resp, n_ley, n_act = len(resp), len(leyes), len(actores)

    s_presencia = sum(1 for n in (n_resp, n_ley, n_act) if n > 0) / 3.0

    con_norma = sum(1 for r in resp if (r.get("id_norma_ref") or r.get("referencia_legal")))
    s_vinculo = (con_norma / n_resp) if n_resp else 0.0

    scores = [float(r.get("confidence_score") or 0.0) for r in resp if r.get("confidence_score") is not None]
    s_rag = (sum(scores) / len(scores)) if scores else 0.0
    s_rag = max(0.0, min(1.0, s_rag))

    sectores = {str(r.get("sector", "")).strip().lower() for r in resp if r.get("sector")}
    s_sector = min(1.0, len(sectores) / 5.0)

    score = round(0.35 * s_presencia + 0.25 * s_vinculo + 0.20 * s_rag + 0.20 * s_sector, 3)

    return {
        "score":         score,
        "n_resp":        n_resp,
        "n_leyes":       n_ley,
        "n_actores":     n_act,
        "pct_con_norma": round(s_vinculo, 2),
        "rag_promedio":  round(s_rag, 2),
        "sectores":      len(sectores),
    }


# ── Detección de citas legales en el texto del plan (regex, sin depender del LLM) ──
_TIPO_NORMA_CANON = {
    "ley": "Ley", "decreto": "Decreto", "decreto ley": "Decreto Ley",
    "resolucion": "Resolución", "resolución": "Resolución",
    "acuerdo": "Acuerdo", "ordenanza": "Ordenanza", "circular": "Circular",
}
_LEY_CITA_RE = re.compile(
    r"\b(decreto\s+ley|ley|decreto|resoluci[oó]n|acuerdo|ordenanza|circular)\s+"
    r"(?:n[o°.º]*\s*)?(\d{1,5})\s+de\s+(\d{4})",
    re.IGNORECASE,
)
_CONPES_CITA_RE = re.compile(r"\bconpes\s+(?:n[o°.º]*\s*)?(\d{3,4})", re.IGNORECASE)


def _extraer_leyes_citadas(plan_text: str, *, max_citas: int = 40) -> list[str]:
    """
    Extrae citas legales explícitas del texto COMPLETO del plan mediante regex
    (ej: 'Ley 715 de 2001', 'Decreto 1077 de 2015', 'Acuerdo 05 de 2024', 'CONPES 3918').

    Es independiente del LLM y del top_k de lectura: garantiza que toda norma
    citada en el documento sea candidata a scraping aunque el agente no la viera.
    """
    if not plan_text:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for m in _LEY_CITA_RE.finditer(plan_text):
        tipo = re.sub(r"\s+", " ", m.group(1).strip().lower())
        canon = _TIPO_NORMA_CANON.get(tipo, m.group(1).strip().capitalize())
        codigo = f"{canon} {m.group(2)} de {m.group(3)}"
        if codigo.lower() not in seen:
            seen.add(codigo.lower())
            out.append(codigo)
            if len(out) >= max_citas:
                return out
    for m in _CONPES_CITA_RE.finditer(plan_text):
        codigo = f"CONPES {m.group(1)}"
        if codigo.lower() not in seen:
            seen.add(codigo.lower())
            out.append(codigo)
            if len(out) >= max_citas:
                break
    return out


async def _scrape_leyes_faltantes(
    *,
    leyes: list[dict[str, Any]],
    rag: RagService,
    settings: Settings,
    all_collections: list[str],
    emit: EmitFn,
    plan_text: str = "",
) -> int:
    """
    Detecta leyes referenciadas en el plan que no están en RAG y las indexa.

    Candidatas = citas explícitas del texto del plan (regex, prioridad) + códigos
    que identificó el agente de leyes. RAG es la fuente: lo que falte se trae con
    el scraper para que el reanálisis posterior lo extraiga ya desde RAG.

    Retorna el número de leyes efectivamente indexadas.
    """
    max_leyes = settings.analysis_scrape_max_laws

    candidatas: list[str] = []
    vistas: set[str] = set()

    # 1) Citas explícitas del texto completo del plan (prioridad)
    for codigo in _extraer_leyes_citadas(plan_text):
        if codigo.lower() not in vistas:
            vistas.add(codigo.lower())
            candidatas.append(codigo)

    # 2) Códigos de leyes identificadas por el agente
    for ley in leyes:
        codigo = str(ley.get("codigo", "")).strip()
        if not codigo or codigo.lower() in vistas:
            continue
        vistas.add(codigo.lower())
        candidatas.append(codigo)

    if not candidatas:
        return 0

    # Verificar cuáles ya están en RAG haciendo una búsqueda rápida
    faltantes: list[str] = []
    for codigo in candidatas[:max_leyes * 3]:  # revisar más candidatas de las que vamos a buscar
        try:
            resp = await rag.search(
                query=codigo,
                collection_ids=all_collections,
                top_k=1,
                score_threshold=0.5,
            )
            if not resp.chunks:
                faltantes.append(codigo)
        except Exception:
            faltantes.append(codigo)

        if len(faltantes) >= max_leyes:
            break

    if not faltantes:
        return 0

    await emit({
        "type": "scraping_laws",
        "msg": f"Buscando {len(faltantes)} ley(es) no encontradas en RAG: {', '.join(faltantes[:3])}{'...' if len(faltantes) > 3 else ''}",
        "leyes": faltantes,
    })

    scraper = ScraperService(settings=settings, rag=rag)
    indexadas = 0
    for codigo in faltantes:
        await emit({"type": "scraping_law", "norma": codigo})
        try:
            resp = await scraper.buscar_normas([codigo], pais=settings.scraper_default_pais)
            if resp.resultados and resp.resultados[0].estado == "indexada":
                indexadas += 1
                await emit({
                    "type": "law_indexed",
                    "codigo": codigo,
                    "chunks": resp.resultados[0].chunks_indexados,
                })
            else:
                motivo = resp.resultados[0].motivo if resp.resultados else "sin resultado"
                await emit({"type": "law_not_found", "codigo": codigo, "motivo": motivo})
        except Exception as exc:
            logger.warning("[ANALYSIS] scraping on-demand norma=%r error=%s", codigo, exc)
            await emit({"type": "law_not_found", "codigo": codigo, "motivo": str(exc)})

    return indexadas


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
    extraccion = await _await_con_progreso(
        extract_document_from_bytes(raw, filename, settings=settings),
        emit=emit,
        msg="Extrayendo texto (OCR en proceso)",
    )

    doc_id = derive_document_id_from_filename(filename)
    all_collections = list(dict.fromkeys([collection_id, *normativa_collection_ids]))

    await emit({"type": "log", "msg": "Indexando plan en Qdrant..."})
    ingesta = await _await_con_progreso(
        rag.ingest_text(
            collection_id=collection_id,
            document_id=doc_id,
            content=extraccion.text,
            chunk_size=700,
            chunk_overlap=120,
            title=titulo_plan or doc_id,
            source_filename=filename,
            chunk_strategy=settings.default_chunk_strategy,
            extraction_method=extraccion.extraction_method.value,
        ),
        emit=emit,
        msg="Indexando plan en Qdrant",
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
    # Texto completo para queries dinámicas (sin truncar — solo se usa para extraer frases)
    plan_text_full = extraccion.text
    # Excerpt corto como fallback si Qdrant no devuelve chunks del plan
    plan_excerpt = extraccion.text[:8_000]
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
                    plan_collection_id=collection_id,
                    plan_doc_id=doc_id,
                    plan_text=plan_text_full,
                    normativa_collection_ids=normativa_collection_ids,
                )
                merge_key = {"leyes": "codigo", "actores": "nombre"}.get(name, "titulo")
                _merge_unique(context[name], rows, key=merge_key)
                await emit({"type": "agent_done", "agent": name, "count": len(context[name])})
            except Exception as exc:
                logger.exception("Agente %s falló", name)
                await emit({"type": "agent_error", "agent": name, "error": str(exc)})

        await asyncio.gather(*(one(a) for a in base_agents))

        # Brechas: se ejecuta DESPUÉS de los demás para poder cruzar información.
        # Se corre en TODOS los niveles de profundidad (basico, estandar, profundo).
        if profundidad in ("basico", "estandar", "profundo"):
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

    # ── Scraping on-demand de leyes referenciadas pero ausentes en RAG ───────
    # Se ejecuta siempre (aunque el agente no haya extraído leyes): las citas del
    # texto completo del plan bastan para detectar normas faltantes en RAG.
    if settings.analysis_scrape_missing_laws:
        leyes_scrapeadas = await _scrape_leyes_faltantes(
            leyes=context["leyes"],
            rag=rag,
            settings=settings,
            all_collections=all_collections,
            emit=emit,
            plan_text=plan_text_full,
        )
        if leyes_scrapeadas:
            # Re-ejecutar agente de leyes con el nuevo conocimiento disponible
            await emit({
                "type": "log",
                "msg": f"{leyes_scrapeadas} ley(es) nuevas indexadas — re-ejecutando agente de leyes...",
            })
            await emit({"type": "agent_start", "agent": "leyes"})
            try:
                nuevas_leyes = await run_agent(
                    rag=rag,
                    http=http,
                    settings=settings,
                    agent="leyes",
                    collection_ids=all_collections,
                    nivel=nivel,
                    profundidad=profundidad,
                    entidad=entidad,
                    extra_query=None,
                    plan_excerpt=plan_excerpt,
                    plan_collection_id=collection_id,
                    plan_doc_id=doc_id,
                    plan_text=plan_text_full,
                    normativa_collection_ids=normativa_collection_ids,
                )
                _merge_unique(context["leyes"], nuevas_leyes, key="codigo")
                await emit({"type": "agent_done", "agent": "leyes", "count": len(context["leyes"])})
            except Exception as exc:
                logger.warning("Re-ejecución agente leyes falló: %s", exc)

    iteraciones = 0
    max_iter = 0 if profundidad == "basico" else (
        max_iteraciones if max_iteraciones is not None else settings.analysis_max_iterations
    )

    umbral = float(settings.analysis_confidence_threshold)

    for iteration in range(1, max_iter + 1):
        iteraciones = iteration

        # Confianza OBJETIVA (no auto-reportada por el LLM) sobre el contexto extraído.
        cobertura = _cobertura_metrics(context)

        # Corte temprano fundamentado: si la cobertura objetiva alcanza el umbral
        # configurado, se finaliza sin gastar más iteraciones ni llamadas al LLM.
        if cobertura["score"] >= umbral:
            await emit(
                {
                    "type": "coordinator_decision",
                    "accion": "finalizar",
                    "razon": (
                        f"Cobertura objetiva {cobertura['score']} ≥ umbral {umbral}: "
                        f"{cobertura['n_resp']} resp, {int(cobertura['pct_con_norma']*100)}% con norma, "
                        f"score RAG {cobertura['rag_promedio']}, {cobertura['sectores']} sectores"
                    ),
                    "confianza": cobertura["score"],
                    "confianza_objetiva": cobertura["score"],
                    "metricas": cobertura,
                }
            )
            break

        await emit({"type": "log", "msg": f"Coordinador iteración {iteration}/{max_iter} (cobertura {cobertura['score']})..."})
        decision = await coordinator_decide(
            http=http,
            settings=settings,
            context=context,
            nivel=nivel,
            profundidad=profundidad,
            iteration=iteration,
            max_iterations=max_iter,
            cobertura=cobertura,
        )
        await emit(
            {
                "type": "coordinator_decision",
                "accion": decision.get("accion"),
                "razon": decision.get("razon"),
                "confianza": decision.get("confianza"),
                "confianza_objetiva": cobertura["score"],
                "metricas": cobertura,
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
                plan_excerpt=plan_excerpt,
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
                event = await asyncio.wait_for(queue.get(), timeout=10.0)
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
