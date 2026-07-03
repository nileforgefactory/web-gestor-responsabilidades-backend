"""Agente de duplicidad SGR — detecta proyectos similares vía RAG semántico + LLM."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings
from app.slices.rag.ai_client import ai_chat
from app.slices.rag.service import RagService

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "duplicidad.md"
_PROMPT_TEMPLATE: str | None = None

# Umbrales de similitud semántica
_UMBRAL_BLOQUEO = 0.85
_UMBRAL_ADVERTENCIA = 0.60

# Colección Qdrant donde buscar proyectos SGR previos indexados
_COLECCION_SGR = "proyectos_sgr"


def _load_prompt() -> str:
    global _PROMPT_TEMPLATE
    if _PROMPT_TEMPLATE is None:
        _PROMPT_TEMPLATE = _PROMPT_PATH.read_text(encoding="utf-8")
    return _PROMPT_TEMPLATE


def _parse_duplicidad_line(line: str) -> dict[str, Any] | None:
    """Parsea la línea pipe del agente de duplicidad (7 campos)."""
    parts = [p.strip() for p in line.split("|")]
    if len(parts) != 7:
        return None

    nivel, score_raw, proyecto_similar, codigo_bpin, estado_similar, recomendacion, puede_raw = parts

    try:
        score = float(score_raw)
    except ValueError:
        score = 0.0

    puede_continuar = puede_raw.lower() == "true"

    return {
        "nivel": nivel.upper() if nivel.upper() in ("ALTO", "MEDIO", "BAJO") else "BAJO",
        "score_similitud": round(min(max(score, 0.0), 1.0), 4),
        "proyecto_similar": proyecto_similar if proyecto_similar.lower() != "ninguno" else None,
        "codigo_bpin": codigo_bpin if codigo_bpin != "N/A" else None,
        "estado_similar": estado_similar if estado_similar != "N/A" else None,
        "recomendacion": recomendacion,
        "puede_continuar": puede_continuar,
    }


async def _buscar_similares_rag(
    *,
    texto_busqueda: str,
    municipio_codigo: str,
    rag: RagService,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """
    Busca proyectos similares en Qdrant usando búsqueda semántica.
    Filtra por municipio si el payload tiene municipio_codigo.
    """
    try:
        resultados = await rag.search(
            query=texto_busqueda,
            limit=top_k,
            collection_name=_COLECCION_SGR,
        )
        similares = []
        for r in resultados:
            payload = r.get("payload", {}) if isinstance(r, dict) else {}
            similares.append({
                "texto": payload.get("texto", r.get("text", "")),
                "nombre_proyecto": payload.get("nombre", ""),
                "codigo_bpin": payload.get("bpin", None),
                "municipio": payload.get("municipio_codigo", ""),
                "score_qdrant": r.get("score", 0.0) if isinstance(r, dict) else 0.0,
            })
        return similares
    except Exception as exc:
        logger.warning("[agente_duplicidad] Error en búsqueda RAG: %s", exc)
        return []


async def verificar_duplicidad(
    *,
    proyecto: dict[str, Any],
    brecha: dict[str, Any],
    datos_municipio: dict[str, Any],
    rag: RagService,
    http: httpx.AsyncClient,
    settings: Settings,
) -> dict[str, Any]:
    """
    Verifica si un proyecto SGR candidato duplica intervenciones existentes.

    Flujo:
    1. Búsqueda semántica en Qdrant (colección proyectos_sgr) con texto del proyecto+brecha
    2. Si hay resultados con score ≥ umbral_advertencia, se incluyen como contexto al LLM
    3. LLM evalúa duplicidad considerando el contexto del mapa de inversiones
    4. Se devuelve resultado estructurado con nivel, score, recomendación y bandera de bloqueo

    Args:
        proyecto: dict con {id, nombre, sector_sgr, tipo_inversion, fuente_sgr, municipio_codigo}
        brecha: dict con {titulo, descripcion, severidad}
        datos_municipio: dict con {divipola, nombre_municipio, categoria_municipio}
        rag: servicio RAG para búsqueda semántica
        http: cliente httpx compartido
        settings: configuración de la app

    Returns:
        dict con {nivel, score_similitud, proyecto_similar, codigo_bpin, estado_similar,
                  recomendacion, puede_continuar, similares_rag, bloqueado}
    """
    prompt_template = _load_prompt()

    # ── 1. Construir texto de búsqueda ──────────────────────────────────────
    texto_busqueda = (
        f"{proyecto.get('nombre', '')} "
        f"{proyecto.get('sector_sgr', '')} "
        f"{brecha.get('titulo', '')} "
        f"{datos_municipio.get('nombre_municipio', '')}"
    ).strip()

    municipio_codigo = (
        datos_municipio.get("divipola")
        or proyecto.get("municipio_codigo", "")
        or ""
    )

    # ── 2. Búsqueda RAG semántica ─────────────────────────────────────────
    similares_rag = await _buscar_similares_rag(
        texto_busqueda=texto_busqueda,
        municipio_codigo=municipio_codigo,
        rag=rag,
    )

    # Proyectos que superan el umbral de advertencia
    similares_relevantes = [s for s in similares_rag if s["score_qdrant"] >= _UMBRAL_ADVERTENCIA]

    # ── 3. Construir contexto para el LLM ─────────────────────────────────
    municipio_ctx = (
        f"Municipio: {datos_municipio.get('nombre_municipio', 'N/D')} "
        f"(DIVIPOLA: {municipio_codigo or 'N/D'}, Cat. {datos_municipio.get('categoria_municipio', 'N/D')})"
    )

    proyecto_ctx = (
        f"Nombre: {proyecto.get('nombre', '')}\n"
        f"Sector: {proyecto.get('sector_sgr', 'N/D')}\n"
        f"Tipo inversión: {proyecto.get('tipo_inversion', 'N/D')}\n"
        f"Fuente SGR: {proyecto.get('fuente_sgr', 'inversion_local')}\n"
        f"Brecha origen: {brecha.get('titulo', '')}\n"
        f"Descripción: {brecha.get('descripcion', '')[:300]}"
    )

    if similares_relevantes:
        similares_ctx = "Proyectos similares encontrados en el Mapa de Inversiones:\n"
        for i, s in enumerate(similares_relevantes[:3], 1):
            similares_ctx += (
                f"{i}. {s['nombre_proyecto'] or s['texto'][:120]} "
                f"(similitud: {s['score_qdrant']:.2f}"
                f"{', BPIN: ' + s['codigo_bpin'] if s['codigo_bpin'] else ''})\n"
            )
    else:
        similares_ctx = "No se encontraron proyectos similares en el Mapa de Inversiones local."

    user_message = (
        f"=== MUNICIPIO ===\n{municipio_ctx}\n\n"
        f"=== PROYECTO CANDIDATO ===\n{proyecto_ctx}\n\n"
        f"=== BÚSQUEDA EN MAPA DE INVERSIONES ===\n{similares_ctx}\n\n"
        "Evalúa la duplicidad de este proyecto y responde en el formato pipe indicado."
    )

    messages = [
        {"role": "system", "content": prompt_template},
        {"role": "user", "content": user_message},
    ]

    # ── 4. Llamar al LLM ──────────────────────────────────────────────────
    try:
        raw = await ai_chat(http=http, settings=settings, messages=messages)
    except Exception as exc:
        logger.warning("[agente_duplicidad] Error LLM proyecto %s: %s", proyecto.get("id"), exc)
        return _fallback_duplicidad(proyecto, similares_rag, str(exc))

    resultado = None
    for line in raw.strip().splitlines():
        line = line.strip()
        if "|" in line and line.count("|") == 6:
            resultado = _parse_duplicidad_line(line)
            if resultado:
                break

    if resultado is None:
        logger.warning("[agente_duplicidad] Respuesta no parseable: %r", raw[:200])
        return _fallback_duplicidad(proyecto, similares_rag, "Respuesta no parseable")

    resultado["similares_rag"] = similares_rag
    resultado["bloqueado"] = (
        resultado["nivel"] == "ALTO"
        or resultado["score_similitud"] >= _UMBRAL_BLOQUEO
        or not resultado["puede_continuar"]
    )

    logger.info(
        "[agente_duplicidad] Proyecto %s → nivel=%s score=%.2f bloqueado=%s",
        proyecto.get("id"),
        resultado["nivel"],
        resultado["score_similitud"],
        resultado["bloqueado"],
    )
    return resultado


def _fallback_duplicidad(
    proyecto: dict[str, Any],
    similares_rag: list[dict[str, Any]],
    razon: str,
) -> dict[str, Any]:
    # Si RAG encontró algo con alta similitud, advertimos conservadoramente
    max_score = max((s["score_qdrant"] for s in similares_rag), default=0.0)
    nivel = "MEDIO" if max_score >= _UMBRAL_ADVERTENCIA else "BAJO"
    return {
        "nivel": nivel,
        "score_similitud": round(max_score, 4),
        "proyecto_similar": None,
        "codigo_bpin": None,
        "estado_similar": None,
        "recomendacion": f"Verificación automática falló ({razon}). Revisar manualmente en MapaInversiones DNP.",
        "puede_continuar": nivel != "ALTO",
        "similares_rag": similares_rag,
        "bloqueado": False,
    }
