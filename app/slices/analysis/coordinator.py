from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import Settings
from app.slices.analysis.parsers import parse_coordinator_json
from app.slices.rag.ollama_client import ollama_chat
from app.slices.rag.service import _with_retries


async def coordinator_decide(
    *,
    http: httpx.AsyncClient,
    settings: Settings,
    context: dict[str, Any],
    nivel: str,
    profundidad: str,
    iteration: int,
    max_iterations: int,
) -> dict[str, Any]:
    """
    Pide al LLM decidir si finalizar, buscar más contexto o profundizar un sector.

    Returns:
        Dict con claves accion, razon, query, sector, confianza.
    """
    resumen_lines = []
    for key in ("responsabilidades", "leyes", "actores", "brechas"):
        items = context.get(key) or []
        resumen_lines.append(f"- {key}: {len(items)} elementos")

    prompt = f"""
Eres coordinador de análisis de planes de desarrollo colombianos.

Resultados:
{chr(10).join(resumen_lines)}

Nivel: {nivel}
Profundidad: {profundidad}
Iteración: {iteration} de {max_iterations}

Responde SOLO JSON:
{{"accion":"finalizar|buscar_mas|reanalizar_sector","razon":"...","query":"...","sector":"...","confianza":0.0}}
""".strip()

    async def call() -> str:
        return await ollama_chat(
            http=http,
            base_url=settings.ollama_base_url,
            model=settings.ollama_chat_model,
            messages=[
                {"role": "system", "content": "Respondes únicamente con JSON válido."},
                {"role": "user", "content": prompt},
            ],
        )

    raw = await _with_retries(call, attempts=3)
    return parse_coordinator_json(raw)
