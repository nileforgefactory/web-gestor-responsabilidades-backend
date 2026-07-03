"""Agente de duplicidad SGR — cascada: Qdrant local → datos.gov.co → LLM."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings
from app.slices.rag.ai_client import ai_chat
from app.slices.sgr.external.mapa_inversiones import (
    buscar_por_texto_bpin,
    buscar_proyectos_municipio,
    indexar_en_qdrant,
)

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "duplicidad.md"
_PROMPT_TEMPLATE: str | None = None

_UMBRAL_BLOQUEO = 0.85
_UMBRAL_ADVERTENCIA = 0.60
_COLECCION_SGR = "proyectos_sgr"


def _load_prompt() -> str:
    global _PROMPT_TEMPLATE
    if _PROMPT_TEMPLATE is None:
        _PROMPT_TEMPLATE = _PROMPT_PATH.read_text(encoding="utf-8")
    return _PROMPT_TEMPLATE


def _parse_duplicidad_line(line: str) -> dict[str, Any] | None:
    parts = [p.strip() for p in line.split("|")]
    if len(parts) != 7:
        return None
    nivel, score_raw, proyecto_similar, codigo_bpin, estado_similar, recomendacion, puede_raw = parts
    try:
        score = float(score_raw)
    except ValueError:
        score = 0.0
    return {
        "nivel": nivel.upper() if nivel.upper() in ("ALTO", "MEDIO", "BAJO") else "BAJO",
        "score_similitud": round(min(max(score, 0.0), 1.0), 4),
        "proyecto_similar": proyecto_similar if proyecto_similar.lower() != "ninguno" else None,
        "codigo_bpin": codigo_bpin if codigo_bpin != "N/A" else None,
        "estado_similar": estado_similar if estado_similar != "N/A" else None,
        "recomendacion": recomendacion,
        "puede_continuar": puede_raw.lower().strip() == "true",
    }


async def _buscar_qdrant(
    *,
    texto: str,
    rag,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Búsqueda semántica local en Qdrant colección proyectos_sgr."""
    try:
        resultados = await rag.search(
            query=texto,
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
                "fuente": payload.get("source", "local"),
            })
        return similares
    except Exception as exc:
        logger.warning("[agente_duplicidad] Qdrant search falló: %s", exc)
        return []


async def _buscar_datos_gov(
    *,
    proyecto: dict[str, Any],
    divipola: str,
    http: httpx.AsyncClient,
    rag,
) -> list[dict[str, Any]]:
    """
    Consulta datos.gov.co, indexa los resultados en Qdrant y devuelve lista normalizada.
    Intenta primero por DIVIPOLA+sector, luego por texto libre.
    """
    proyectos_dnp = await buscar_proyectos_municipio(
        divipola=divipola,
        sector=proyecto.get("sector_sgr"),
        http=http,
    )

    if not proyectos_dnp:
        # Fallback: búsqueda de texto libre por nombre del proyecto
        proyectos_dnp = await buscar_por_texto_bpin(
            texto=proyecto.get("nombre", ""),
            http=http,
        )

    if proyectos_dnp:
        # Indexar en Qdrant para consultas futuras (sin await bloqueante)
        try:
            await indexar_en_qdrant(proyectos=proyectos_dnp, rag=rag, divipola=divipola)
        except Exception as exc:
            logger.warning("[agente_duplicidad] indexar_en_qdrant falló: %s", exc)

    # Devolver en formato estándar de similares
    return [
        {
            "texto": p.get("objeto") or p.get("nombre", ""),
            "nombre_proyecto": p.get("nombre", ""),
            "codigo_bpin": p.get("bpin"),
            "municipio": divipola,
            "estado": p.get("estado", "DESCONOCIDO"),
            "score_qdrant": 0.0,  # no tenemos score semántico aún
            "fuente": "datos_gov_co",
        }
        for p in proyectos_dnp
    ]


async def verificar_duplicidad(
    *,
    proyecto: dict[str, Any],
    brecha: dict[str, Any],
    datos_municipio: dict[str, Any],
    rag,
    http: httpx.AsyncClient,
    settings: Settings,
) -> dict[str, Any]:
    """
    Verifica duplicidad mediante cascada de 3 pasos:

    1. Búsqueda semántica en Qdrant (proyectos indexados localmente)
    2. Si no hay resultados relevantes (≥ umbral) → consulta datos.gov.co e indexa
    3. LLM evalúa duplicidad con el contexto obtenido

    Returns:
        dict con {nivel, score_similitud, proyecto_similar, codigo_bpin, estado_similar,
                  recomendacion, puede_continuar, similares_rag, bloqueado, fuente_datos}
    """
    prompt_template = _load_prompt()

    texto_busqueda = (
        f"{proyecto.get('nombre', '')} "
        f"{proyecto.get('sector_sgr', '')} "
        f"{brecha.get('titulo', '')} "
        f"{datos_municipio.get('nombre_municipio', '')}"
    ).strip()

    divipola = (
        datos_municipio.get("divipola")
        or proyecto.get("municipio_codigo", "")
        or ""
    )

    # ── Paso 1: Qdrant local ──────────────────────────────────────────────
    similares_qdrant = await _buscar_qdrant(texto=texto_busqueda, rag=rag)
    relevantes_local = [s for s in similares_qdrant if s["score_qdrant"] >= _UMBRAL_ADVERTENCIA]

    fuente_datos = "qdrant_local"
    similares_externos: list[dict[str, Any]] = []

    # ── Paso 2: datos.gov.co si Qdrant no tiene resultados relevantes ─────
    if not relevantes_local and divipola:
        logger.info(
            "[agente_duplicidad] Sin resultados locales para DIVIPOLA %s — consultando datos.gov.co",
            divipola,
        )
        similares_externos = await _buscar_datos_gov(
            proyecto=proyecto,
            divipola=divipola,
            http=http,
            rag=rag,
        )
        fuente_datos = "datos_gov_co" if similares_externos else "sin_datos"

        # Segunda búsqueda en Qdrant ahora que se indexaron los datos del DNP
        if similares_externos:
            similares_qdrant = await _buscar_qdrant(texto=texto_busqueda, rag=rag)
            relevantes_local = [s for s in similares_qdrant if s["score_qdrant"] >= _UMBRAL_ADVERTENCIA]
            if relevantes_local:
                fuente_datos = "datos_gov_co+qdrant"

    # ── Paso 3: Construir contexto para el LLM ────────────────────────────
    municipio_ctx = (
        f"Municipio: {datos_municipio.get('nombre_municipio', 'N/D')} "
        f"(DIVIPOLA: {divipola or 'N/D'}, Cat. {datos_municipio.get('categoria_municipio', 'N/D')})"
    )

    proyecto_ctx = (
        f"Nombre: {proyecto.get('nombre', '')}\n"
        f"Sector: {proyecto.get('sector_sgr', 'N/D')}\n"
        f"Tipo inversión: {proyecto.get('tipo_inversion', 'N/D')}\n"
        f"Fuente SGR: {proyecto.get('fuente_sgr', 'inversion_local')}\n"
        f"Brecha origen: {brecha.get('titulo', '')}\n"
        f"Descripción: {brecha.get('descripcion', '')[:300]}"
    )

    todos_similares = relevantes_local or similares_externos
    if todos_similares:
        similares_ctx = f"Proyectos similares encontrados (fuente: {fuente_datos}):\n"
        for i, s in enumerate(todos_similares[:4], 1):
            score_info = f", similitud: {s['score_qdrant']:.2f}" if s["score_qdrant"] > 0 else ""
            bpin_info = f", BPIN: {s['codigo_bpin']}" if s.get("codigo_bpin") else ""
            estado_info = f", estado: {s.get('estado', '')}" if s.get("estado") else ""
            similares_ctx += (
                f"{i}. {s['nombre_proyecto'] or s['texto'][:150]}"
                f"{score_info}{bpin_info}{estado_info}\n"
            )
    else:
        similares_ctx = (
            "No se encontraron proyectos similares en el repositorio local "
            "ni en datos.gov.co para este municipio y sector."
        )

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

    # ── Paso 4: LLM ───────────────────────────────────────────────────────
    try:
        raw = await ai_chat(http=http, settings=settings, messages=messages)
    except Exception as exc:
        logger.warning("[agente_duplicidad] Error LLM proyecto %s: %s", proyecto.get("id"), exc)
        return _fallback_duplicidad(proyecto, similares_qdrant, similares_externos, fuente_datos, str(exc))

    resultado = None
    for line in raw.strip().splitlines():
        line = line.strip()
        if "|" in line and line.count("|") == 6:
            resultado = _parse_duplicidad_line(line)
            if resultado:
                break

    if resultado is None:
        logger.warning("[agente_duplicidad] Respuesta no parseable: %r", raw[:200])
        return _fallback_duplicidad(proyecto, similares_qdrant, similares_externos, fuente_datos, "Respuesta no parseable")

    # Combinar similares para el response
    similares_combinados = similares_qdrant + [
        s for s in similares_externos
        if not any(s["nombre_proyecto"] == q["nombre_proyecto"] for q in similares_qdrant)
    ]

    resultado["similares_rag"] = similares_combinados
    resultado["fuente_datos"] = fuente_datos
    resultado["bloqueado"] = (
        resultado["nivel"] == "ALTO"
        or resultado["score_similitud"] >= _UMBRAL_BLOQUEO
        or not resultado["puede_continuar"]
    )

    logger.info(
        "[agente_duplicidad] Proyecto %s → nivel=%s score=%.2f fuente=%s bloqueado=%s",
        proyecto.get("id"),
        resultado["nivel"],
        resultado["score_similitud"],
        fuente_datos,
        resultado["bloqueado"],
    )
    return resultado


def _fallback_duplicidad(
    proyecto: dict[str, Any],
    similares_qdrant: list[dict[str, Any]],
    similares_externos: list[dict[str, Any]],
    fuente_datos: str,
    razon: str,
) -> dict[str, Any]:
    todos = similares_qdrant + similares_externos
    max_score = max((s.get("score_qdrant", 0.0) for s in todos), default=0.0)
    nivel = "MEDIO" if max_score >= _UMBRAL_ADVERTENCIA else "BAJO"
    return {
        "nivel": nivel,
        "score_similitud": round(max_score, 4),
        "proyecto_similar": None,
        "codigo_bpin": None,
        "estado_similar": None,
        "recomendacion": (
            f"Verificación automática falló ({razon}). "
            "Revisar manualmente en MapaInversiones DNP y datos.gov.co."
        ),
        "puede_continuar": nivel != "ALTO",
        "similares_rag": todos,
        "fuente_datos": fuente_datos,
        "bloqueado": False,
    }
