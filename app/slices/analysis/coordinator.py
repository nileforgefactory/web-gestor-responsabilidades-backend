from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import Settings
from app.slices.analysis.parsers import parse_coordinator_json
from app.slices.rag.chat_provider import chat_llm
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
    cobertura: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Pide al LLM decidir si finalizar, buscar más contexto o profundizar un sector.

    Recibe ``cobertura``: métricas OBJETIVAS del análisis (confianza calculada
    sobre señales medibles), para que la decisión tenga soporte real y no se base
    solo en una confianza auto-reportada.

    Returns:
        Dict con claves accion, razon, query, sector, confianza.
    """
    resumen_lines = []
    for key in ("responsabilidades", "leyes", "actores", "brechas"):
        items = context.get(key) or []
        resumen_lines.append(f"- {key}: {len(items)} elementos")

    cobertura = cobertura or {}
    cobertura_txt = (
        f"""Cobertura objetiva (0-1): {cobertura.get('score', 'n/d')}
  · responsabilidades con norma vinculada: {int(cobertura.get('pct_con_norma', 0) * 100)}%
  · score RAG promedio (similitud de evidencia): {cobertura.get('rag_promedio', 'n/d')}
  · sectores distintos cubiertos: {cobertura.get('sectores', 'n/d')}"""
        if cobertura
        else "Cobertura objetiva: no disponible"
    )

    prompt = f"""
Eres coordinador de análisis de planes de desarrollo colombianos.

Resultados:
{chr(10).join(resumen_lines)}

{cobertura_txt}

Nivel: {nivel}
Profundidad: {profundidad}
Iteración: {iteration} de {max_iterations}

Usa la cobertura objetiva como base de tu decisión:
- Si la cobertura es alta y consistente, responde "finalizar".
- Si faltan vínculos normativos o sectores clave, responde "buscar_mas" (define "query") o "reanalizar_sector" (define "sector").
El campo "confianza" debe reflejar la cobertura objetiva, no una estimación arbitraria.

Responde SOLO JSON:
{{"accion":"finalizar|buscar_mas|reanalizar_sector","razon":"...","query":"...","sector":"...","confianza":0.0}}
""".strip()

    async def call() -> str:
        return await chat_llm(
            http=http,
            settings=settings,
            messages=[
                {"role": "system", "content": "Respondes únicamente con JSON válido."},
                {"role": "user", "content": prompt},
            ],
        )

    raw = await _with_retries(call, attempts=3)
    return parse_coordinator_json(raw)
