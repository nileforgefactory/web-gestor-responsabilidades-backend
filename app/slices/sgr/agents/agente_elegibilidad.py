"""Agente de elegibilidad SGR — evalúa si una brecha es financiable con SGR Cat. 5/6."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings
from app.slices.rag.ai_client import ai_chat

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "elegibilidad.md"
_PROMPT_TEMPLATE: str | None = None


def _load_prompt() -> str:
    global _PROMPT_TEMPLATE
    if _PROMPT_TEMPLATE is None:
        _PROMPT_TEMPLATE = _PROMPT_PATH.read_text(encoding="utf-8")
    return _PROMPT_TEMPLATE


# Sectores SGR reconocidos — para validación rápida
SECTORES_SGR = {
    "Agua potable y saneamiento",
    "Transporte",
    "Educación",
    "Salud",
    "Deporte y recreación",
    "Cultura",
    "Vivienda",
    "Medio ambiente",
    "Agropecuario",
    "Ciencia tecnología e innovación",
    "Prevención y atención de desastres",
    "Fortalecimiento institucional",
    "Justicia y seguridad",
    "Equipamiento municipal",
}

# Mapa fuente → etiqueta legible
FUENTE_LABELS = {
    "inversion_local": "Asignación Inversión Local (sin OCAD)",
    "inversion_regional": "Inversión Regional (OCAD Departamental/Regional)",
    "ctei": "CTeI (OCAD CTeI)",
    "paz": "Asignación para la Paz (OCAD Paz)",
    "asignacion_directa": "Asignación Directa (municipio productor)",
    "no_aplica": "No aplica para SGR",
}


def _parse_elegibilidad_line(line: str) -> dict[str, Any] | None:
    """Parsea una línea del formato pipe del agente de elegibilidad."""
    parts = [p.strip() for p in line.split("|")]
    if len(parts) != 7:
        return None

    elegible_raw, sector, subsector, fuente, razon, condiciones, tipo_inversion = parts

    elegible_raw = elegible_raw.lower()
    if elegible_raw == "true":
        elegible = True
        condicional = False
    elif elegible_raw == "condicional":
        elegible = True
        condicional = True
    else:
        elegible = False
        condicional = False

    condiciones_list = (
        [c.strip() for c in condiciones.split(";") if c.strip() and c.strip().lower() != "ninguna"]
        if condiciones
        else []
    )

    return {
        "elegible": elegible,
        "condicional": condicional,
        "sector_sgr": sector if sector in SECTORES_SGR else sector,
        "subsector": subsector if subsector != "N/A" else None,
        "fuente_recomendada": fuente,
        "fuente_label": FUENTE_LABELS.get(fuente, fuente),
        "razon": razon,
        "condiciones": condiciones_list,
        "tipo_inversion": tipo_inversion,
    }


async def evaluar_elegibilidad(
    *,
    brecha: dict[str, Any],
    datos_municipio: dict[str, Any],
    http: httpx.AsyncClient,
    settings: Settings,
) -> dict[str, Any]:
    """
    Evalúa si una brecha es elegible para financiación SGR Cat. 5/6.

    Args:
        brecha: dict con campos {id, titulo, descripcion, sector, severidad,
                referencia_legal, tipo_detallado, recomendacion}
        datos_municipio: dict con {divipola, categoria_municipio, nbi, icld,
                         departamento, region_geografica, nombre_municipio}
        http: cliente httpx compartido
        settings: configuración de la app

    Returns:
        dict con resultado de elegibilidad enriquecido con datos de la brecha.
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

    brecha_ctx = (
        f"Título: {brecha.get('titulo', '')}\n"
        f"Descripción: {brecha.get('descripcion', '')}\n"
        f"Sector: {brecha.get('sector', 'N/D')}\n"
        f"Severidad: {brecha.get('severidad', 'N/D')}\n"
        f"Tipo jurídico: {brecha.get('tipo_detallado', brecha.get('tipo', 'N/D'))}\n"
        f"Referencia legal: {brecha.get('referencia_legal', 'N/D')}\n"
        f"Recomendación: {brecha.get('recomendacion', '')}"
    )

    messages = [
        {"role": "system", "content": prompt_template},
        {
            "role": "user",
            "content": (
                f"=== DATOS DEL MUNICIPIO ===\n{municipio_ctx}\n\n"
                f"=== BRECHA DETECTADA ===\n{brecha_ctx}\n\n"
                "Evalúa la elegibilidad SGR de esta brecha siguiendo el formato indicado."
            ),
        },
    ]

    try:
        raw = await ai_chat(http=http, settings=settings, messages=messages)
    except Exception as exc:
        logger.warning("[agente_elegibilidad] Error LLM para brecha %s: %s", brecha.get("id"), exc)
        return _fallback_no_elegible(brecha, str(exc))

    # Buscar la primera línea que tenga exactamente 7 campos
    resultado = None
    for line in raw.strip().splitlines():
        line = line.strip()
        if "|" in line and line.count("|") == 6:
            resultado = _parse_elegibilidad_line(line)
            if resultado:
                break

    if resultado is None:
        logger.warning("[agente_elegibilidad] Respuesta no parseable: %r", raw[:200])
        return _fallback_no_elegible(brecha, "Respuesta del LLM no parseable")

    resultado["brecha_id"] = brecha.get("id")
    resultado["brecha_titulo"] = brecha.get("titulo", "")
    resultado["brecha_severidad"] = brecha.get("severidad", "baja")
    resultado["brecha_sector"] = brecha.get("sector", "")
    resultado["raw_llm"] = raw[:500]

    logger.info(
        "[agente_elegibilidad] Brecha %s → elegible=%s sector=%s fuente=%s",
        brecha.get("id"),
        resultado["elegible"],
        resultado["sector_sgr"],
        resultado["fuente_recomendada"],
    )
    return resultado


def _fallback_no_elegible(brecha: dict[str, Any], razon: str) -> dict[str, Any]:
    return {
        "brecha_id": brecha.get("id"),
        "brecha_titulo": brecha.get("titulo", ""),
        "brecha_severidad": brecha.get("severidad", "baja"),
        "brecha_sector": brecha.get("sector", ""),
        "elegible": False,
        "condicional": False,
        "sector_sgr": brecha.get("sector", "Indefinido"),
        "subsector": None,
        "fuente_recomendada": "no_aplica",
        "fuente_label": "No evaluado (error)",
        "razon": razon,
        "condiciones": [],
        "tipo_inversion": "",
        "raw_llm": "",
    }
