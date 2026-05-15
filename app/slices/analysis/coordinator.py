"""
Agente coordinador: decide si el análisis es suficiente
o si debe buscar más contexto / reanalizar un sector.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.slices.analysis.agents import _llm_call_with_retry
from app.slices.rag.service import RagService

logger = logging.getLogger(__name__)

_COORDINATOR_SYSTEM = (
    "Eres el coordinador de un sistema de análisis de planes de desarrollo colombianos. "
    "Evalúas si el análisis es suficiente o necesitas más información. "
    "Responde SOLO con JSON válido, sin texto adicional."
)

_COORDINATOR_TEMPLATE = """\
Has recibido los resultados preliminares de los agentes especializados.

Resultados actuales:
{resumen_resultados}

Contexto del plan:
- Nivel: {nivel}
- Sectores declarados: {sectores}
- Profundidad solicitada: {profundidad}
- Iteración actual: {iteracion} de {max_iteraciones}

Decide una acción:
1. "finalizar" — el análisis es suficiente (responsabilidades, leyes y actores tienen resultados)
2. "buscar_mas" — necesito más contexto, indica query específica
3. "reanalizar_sector" — un sector tiene cobertura insuficiente, indica cuál

Responde SOLO con este JSON (sin texto extra):
{{
  "accion": "finalizar|buscar_mas|reanalizar_sector",
  "razon": "explicación breve",
  "query": "query para buscar (solo si accion=buscar_mas)",
  "sector": "sector a reanalizar (solo si accion=reanalizar_sector)",
  "confianza": 0.0
}}
"""


def _build_resumen(context: dict[str, Any]) -> str:
    lines = []
    for agent, results in context.items():
        if agent == "extra_chunks":
            continue
        count = len(results) if isinstance(results, list) else 0
        if count:
            lines.append(f"- {agent}: {count} elementos extraídos")
        else:
            lines.append(f"- {agent}: SIN RESULTADOS")

    sectores_cubiertos = {
        r.get("sector", "")
        for r in context.get("responsabilidades", [])
        if r.get("sector")
    }
    if sectores_cubiertos:
        lines.append(f"Sectores con responsabilidades: {', '.join(sectores_cubiertos)}")
    return "\n".join(lines)


async def coordinator_decide(
    rag: RagService,
    context: dict[str, Any],
    nivel: str,
    sectores: list[str],
    profundidad: str,
    iteration: int,
    max_iterations: int,
) -> dict[str, Any]:
    resumen = _build_resumen(context)
    user = _COORDINATOR_TEMPLATE.format(
        resumen_resultados=resumen,
        nivel=nivel,
        sectores=", ".join(sectores) if sectores else "no especificados",
        profundidad=profundidad,
        iteracion=iteration,
        max_iteraciones=max_iterations,
    )

    try:
        raw = await _llm_call_with_retry(
            rag.http,
            rag.settings.ollama_base_url,
            rag.settings.ollama_chat_model,
            _COORDINATOR_SYSTEM,
            user,
            label="coordinator",
        )
        # Extraer JSON del response (puede venir con texto adicional)
        import re
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        return json.loads(raw)
    except (json.JSONDecodeError, RuntimeError) as exc:
        logger.warning("Coordinador retornó respuesta inválida: %s", exc)
        # Por defecto: finalizar si hay suficientes resultados
        tiene_resultados = all(
            len(context.get(k, [])) > 0
            for k in ("responsabilidades", "leyes", "actores")
        )
        accion = "finalizar" if tiene_resultados else "buscar_mas"
        return {
            "accion": accion,
            "razon": "respuesta inválida del coordinador — decisión automática",
            "confianza": 0.5,
        }
