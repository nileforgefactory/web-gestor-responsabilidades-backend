"""Agente MGA — genera las 4 secciones de la Ficha MGA Web para un proyecto SGR."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings
from app.slices.rag.ai_client import ai_chat

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "mga.md"
_PROMPT_TEMPLATE: str | None = None

# Campos MGA que extraemos del XML
_MGA_FIELDS = ("identificacion", "preparacion", "evaluacion", "programacion")


def _load_prompt() -> str:
    global _PROMPT_TEMPLATE
    if _PROMPT_TEMPLATE is None:
        _PROMPT_TEMPLATE = _PROMPT_PATH.read_text(encoding="utf-8")
    return _PROMPT_TEMPLATE


def _parse_mga_xml(raw: str) -> dict[str, str | None]:
    """Extrae las 4 secciones del XML que devuelve el LLM."""
    result: dict[str, str | None] = {f: None for f in _MGA_FIELDS}
    for field in _MGA_FIELDS:
        pattern = rf"<{field}>(.*?)</{field}>"
        match = re.search(pattern, raw, re.DOTALL)
        if match:
            result[field] = match.group(1).strip()
    return result


async def generar_ficha_mga(
    *,
    proyecto: dict[str, Any],
    brecha: dict[str, Any],
    datos_municipio: dict[str, Any],
    plan_chunks: list[str],
    http: httpx.AsyncClient,
    settings: Settings,
) -> dict[str, Any]:
    """
    Genera el contenido de las 4 secciones MGA para un proyecto SGR candidato.

    Args:
        proyecto: dict con campos del ProyectoSGR {id, nombre, sector_sgr,
                  tipo_inversion, fuente_sgr, razon_elegibilidad, ...}
        brecha: dict con la brecha origen {titulo, descripcion, severidad,
                referencia_legal, recomendacion}
        datos_municipio: dict con {divipola, nombre_municipio, categoria_municipio,
                         nbi, icld, departamento, region_geografica}
        plan_chunks: fragmentos relevantes del plan de desarrollo (RAG)
        http: cliente httpx compartido
        settings: configuración de la app

    Returns:
        dict con {identificacion, preparacion, evaluacion, programacion,
                  campos_completos, modelo_usado}
    """
    prompt_template = _load_prompt()

    municipio_ctx = (
        f"Municipio: {datos_municipio.get('nombre_municipio', 'N/D')}\n"
        f"DIVIPOLA: {datos_municipio.get('divipola', 'N/D')}\n"
        f"Categoría: {datos_municipio.get('categoria_municipio', 'N/D')}\n"
        f"NBI: {datos_municipio.get('nbi', 'N/D')}%\n"
        f"ICLD: {datos_municipio.get('icld', 'N/D')} SMMLV\n"
        f"Departamento: {datos_municipio.get('departamento', 'N/D')}\n"
        f"Región: {datos_municipio.get('region_geografica', 'N/D')}"
    )

    proyecto_ctx = (
        f"Nombre del proyecto: {proyecto.get('nombre', '')}\n"
        f"Sector SGR: {proyecto.get('sector_sgr', 'N/D')}\n"
        f"Tipo de inversión: {proyecto.get('tipo_inversion', 'N/D')}\n"
        f"Fuente SGR recomendada: {proyecto.get('fuente_sgr', 'inversion_local')}\n"
        f"Justificación de elegibilidad: {proyecto.get('razon_elegibilidad', '')}\n"
        f"Score de viabilidad: {proyecto.get('score_sgr', 'N/D')}"
    )

    brecha_ctx = (
        f"Brecha identificada: {brecha.get('titulo', '')}\n"
        f"Descripción del problema: {brecha.get('descripcion', '')}\n"
        f"Severidad: {brecha.get('severidad', 'N/D')}\n"
        f"Referencia legal: {brecha.get('referencia_legal', 'N/D')}\n"
        f"Recomendación de política: {brecha.get('recomendacion', '')}"
    )

    plan_ctx = ""
    if plan_chunks:
        fragmentos = "\n---\n".join(plan_chunks[:5])  # máx 5 chunks del plan
        plan_ctx = f"\n\n=== EXTRACTOS DEL PLAN DE DESARROLLO ===\n{fragmentos}"

    user_message = (
        f"=== MUNICIPIO ===\n{municipio_ctx}\n\n"
        f"=== PROYECTO SGR CANDIDATO ===\n{proyecto_ctx}\n\n"
        f"=== BRECHA DE ORIGEN ===\n{brecha_ctx}"
        f"{plan_ctx}\n\n"
        "Genera la ficha MGA completa para este proyecto en el formato XML indicado."
    )

    messages = [
        {"role": "system", "content": prompt_template},
        {"role": "user", "content": user_message},
    ]

    try:
        raw = await ai_chat(http=http, settings=settings, messages=messages)
    except Exception as exc:
        logger.warning("[agente_mga] Error LLM para proyecto %s: %s", proyecto.get("id"), exc)
        return _fallback_mga(proyecto, str(exc))

    secciones = _parse_mga_xml(raw)
    campos_completos = sum(1 for v in secciones.values() if v)

    if campos_completos == 0:
        logger.warning("[agente_mga] XML no parseable para proyecto %s: %r", proyecto.get("id"), raw[:200])
        return _fallback_mga(proyecto, "Respuesta del LLM no parseable como XML MGA")

    modelo = getattr(settings, "ollama_chat_model", None) or "llm"
    logger.info(
        "[agente_mga] Proyecto %s → %d/4 secciones generadas",
        proyecto.get("id"),
        campos_completos,
    )

    return {
        **secciones,
        "campos_completos": campos_completos,
        "modelo_usado": modelo,
    }


def _fallback_mga(proyecto: dict[str, Any], razon: str) -> dict[str, Any]:
    nombre = proyecto.get("nombre", "")
    return {
        "identificacion": (
            f"[Error al generar] Proyecto: {nombre}. Razón: {razon}. "
            "Complete manualmente esta sección en la MGA Web."
        ),
        "preparacion": None,
        "evaluacion": None,
        "programacion": None,
        "campos_completos": 0,
        "modelo_usado": None,
    }
