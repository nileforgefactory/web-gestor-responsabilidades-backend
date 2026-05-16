from __future__ import annotations

import logging
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)

from app.core.config import Settings
from app.slices.analysis import parsers
from app.slices.analysis.prompt_builder import build_agent_prompt
from app.slices.analysis.rag_context import chunks_to_context_blob, fetch_agent_chunks
from app.slices.rag.ollama_client import ollama_chat
from app.slices.rag.service import RagService, _with_retries

# http y settings se mantienen en la firma de run_matriz_agent por compatibilidad con el caller

PARSER_BY_AGENT: dict[str, Callable[[str], list[dict[str, Any]]]] = {
    "responsabilidades": parsers.parse_responsabilidades,
    "leyes": parsers.parse_leyes,
    "actores": parsers.parse_actores,
    "brechas": parsers.parse_brechas,
}


async def run_agent(
    *,
    rag: RagService,
    http: httpx.AsyncClient,
    settings: Settings,
    agent: str,
    collection_ids: list[str],
    nivel: str,
    profundidad: str,
    entidad: str = "",
    extra_query: str | None = None,
    plan_excerpt: str = "",
) -> list[dict[str, Any]]:
    """
    Ejecuta un agente especializado: RAG + prompt + parseo de líneas estructuradas.

    Returns:
        Lista de dicts con campos del agente y ``chunk_ids`` / ``confidence_score``.
    """
    logger.info("[AGENT:%s] Iniciando — nivel=%s profundidad=%s extra_query=%r", agent, nivel, profundidad, extra_query)

    chunks = await fetch_agent_chunks(
        rag,
        collection_ids=collection_ids,
        agent=agent,
        extra_query=extra_query,
    )
    chunk_ids = [c.chunk_id for c in chunks]
    context_blob = chunks_to_context_blob(chunks)

    logger.info("[AGENT:%s] RAG devolvió %d chunks — IDs: %s", agent, len(chunks), chunk_ids[:5])
    if not chunks:
        logger.warning("[AGENT:%s] ⚠ Sin chunks — el modelo recibirá contexto vacío", agent)

    system = build_agent_prompt(agent, nivel=nivel, profundidad=profundidad, entidad=entidad)
    user_parts = []
    if plan_excerpt:
        user_parts.append(f"Fragmento del plan analizado:\n{plan_excerpt[:6000]}\n")
    user_parts.append(f"Contexto RAG recuperado:\n{context_blob}\n")
    user_parts.append("Extrae según el formato indicado en el system prompt.")

    async def call() -> str:
        return await ollama_chat(
            http=http,
            base_url=settings.ollama_base_url,
            model=settings.ollama_chat_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": "\n".join(user_parts)},
            ],
        )

    raw = await _with_retries(call, attempts=3)
    parser = PARSER_BY_AGENT.get(agent)
    if not parser:
        return []
    items = parser(raw)
    logger.info("[AGENT:%s] Parser extrajo %d items de la respuesta del LLM", agent, len(items))
    if not items:
        logger.warning("[AGENT:%s] ⚠ Parser devolvió 0 items — respuesta cruda (500 chars): %s", agent, raw[:500])
    for item in items:
        item["chunk_ids"] = chunk_ids
        item["confidence_score"] = (
            sum(c.score for c in chunks) / len(chunks) if chunks else 0.0
        )
    return items


def build_matriz(context: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Construye la matriz de competencias territoriales de forma determinista
    cruzando responsabilidades, actores y leyes ya extraídos.

    Reglas de asignación por nivel del actor:
      municipal      → municipio = tipo_resp, resto N (salvo concurrente)
      departamental  → departamento = tipo_resp
      nacional       → nacion = tipo_resp
      especializado  → especializado = tipo_resp
    Si el tipo de responsabilidad es 'C' se marca concurrente en todos los niveles
    donde hay actor. Brechas: si no hay actor → critica; tipo C con un solo actor → duplicidad.
    """
    responsabilidades: list[dict[str, Any]] = context.get("responsabilidades", [])
    actores: list[dict[str, Any]] = context.get("actores", [])
    brechas_ctx: list[dict[str, Any]] = context.get("brechas", [])

    # Índice de brechas por título (normalizado) para cruzar
    brechas_index: dict[str, str] = {
        str(b.get("titulo", "")).lower()[:40]: str(b.get("tipo", "ok"))
        for b in brechas_ctx
    }

    # Índice de niveles de actores: nombre_lower → nivel
    actor_niveles: dict[str, str] = {
        str(a.get("nombre", "")).lower(): str(a.get("nivel", "municipal"))
        for a in actores
    }

    # Niveles presentes en los actores extraídos
    niveles_presentes: set[str] = {v for v in actor_niveles.values()}

    def _tipo(resp_tipo: str, nivel_actor: str, niveles: set[str]) -> str:
        t = str(resp_tipo).upper()[:1] or "P"
        if t not in ("P", "C", "S", "N"):
            t = "P"
        if t == "C":
            return "C"
        # Si hay actor de otro nivel también → concurrente
        otros = niveles - {nivel_actor}
        if otros and t == "P":
            return "C" if len(niveles) > 1 else "P"
        return t

    def _brecha(resp: dict[str, Any], nivel_count: int) -> str:
        titulo_key = str(resp.get("titulo", "")).lower()[:40]
        if titulo_key in brechas_index:
            return brechas_index[titulo_key]
        if nivel_count == 0:
            return "critica"
        if nivel_count > 1 and str(resp.get("tipo", "P")).upper() == "P":
            return "duplicidad"
        return "ok"

    matriz: list[dict[str, Any]] = []
    seen: set[str] = set()

    for resp in responsabilidades:
        titulo = str(resp.get("titulo", "")).strip()
        if not titulo:
            continue
        key = titulo.lower()[:50]
        if key in seen:
            continue
        seen.add(key)

        sector = str(resp.get("sector", "")).strip()
        ley_base = str(resp.get("referencia_legal") or "").strip()
        resp_tipo = str(resp.get("tipo", "P")).upper()[:1]

        # Determinar valores por columna basándose en actores presentes
        col: dict[str, str] = {"nacion": "N", "departamento": "N", "municipio": "N", "especializado": "N"}
        nivel_mapa = {
            "nacional": "nacion",
            "departamental": "departamento",
            "municipal": "municipio",
            "especializado": "especializado",
        }

        for nivel_actor, col_key in nivel_mapa.items():
            if nivel_actor in niveles_presentes:
                col[col_key] = _tipo(resp_tipo, nivel_actor, niveles_presentes)

        # Si no hay ningún nivel detectado, usar nivel del plan como municipio=P
        if all(v == "N" for v in col.values()):
            col["municipio"] = "P"

        nivel_count = sum(1 for v in col.values() if v != "N")

        matriz.append({
            "competencia":  titulo,
            "ley_base":     ley_base,
            "nacion":       col["nacion"],
            "departamento": col["departamento"],
            "municipio":    col["municipio"],
            "especializado": col["especializado"],
            "sector":       sector,
            "brecha":       _brecha(resp, nivel_count),
        })

    return matriz


async def run_matriz_agent(
    *,
    http: httpx.AsyncClient,
    settings: Settings,
    context: dict[str, Any],
    nivel: str,
    profundidad: str,
) -> list[dict[str, Any]]:
    """Construye la matriz de competencias de forma determinista (sin LLM)."""
    return build_matriz(context)
