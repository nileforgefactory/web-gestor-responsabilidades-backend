from __future__ import annotations

from typing import Any, Callable

import httpx

from app.core.config import Settings
from app.slices.analysis import parsers
from app.slices.analysis.prompt_builder import build_agent_prompt
from app.slices.analysis.rag_context import chunks_to_context_blob, fetch_agent_chunks
from app.slices.rag.ollama_client import ollama_chat
from app.slices.rag.service import RagService, _with_retries

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
    chunks = await fetch_agent_chunks(
        rag,
        collection_ids=collection_ids,
        agent=agent,
        extra_query=extra_query,
    )
    chunk_ids = [c.chunk_id for c in chunks]
    context_blob = chunks_to_context_blob(chunks)

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
    for item in items:
        item["chunk_ids"] = chunk_ids
        item["confidence_score"] = (
            sum(c.score for c in chunks) / len(chunks) if chunks else 0.0
        )
    return items


async def run_matriz_agent(
    *,
    http: httpx.AsyncClient,
    settings: Settings,
    context: dict[str, Any],
    nivel: str,
    profundidad: str,
) -> list[dict[str, Any]]:
    system = build_agent_prompt("matriz", nivel=nivel, profundidad=profundidad)
    summary = {
        "responsabilidades": context.get("responsabilidades", [])[:40],
        "leyes": context.get("leyes", [])[:30],
        "actores": context.get("actores", [])[:30],
        "brechas": context.get("brechas", [])[:20],
    }
    import json

    user = (
        "Consolida esta información en la matriz JSON:\n"
        + json.dumps(summary, ensure_ascii=False, indent=2)
    )

    async def call() -> str:
        return await ollama_chat(
            http=http,
            base_url=settings.ollama_base_url,
            model=settings.ollama_chat_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )

    raw = await _with_retries(call, attempts=3)
    return parsers.parse_matriz_json(raw)
