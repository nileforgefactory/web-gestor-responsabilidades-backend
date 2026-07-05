"""Agente evaluador SGR — Modo 2: diagnóstico inverso de proyectos existentes."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings
from app.slices.rag.ai_client import ai_chat

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "evaluador.md"
_PROMPT_TEMPLATE: str | None = None

# Umbrales para clasificación en cuadrantes
_UMBRAL_ESTRUCTURA = 0.65
_UMBRAL_ALINEACION = 0.60

# Pesos para score_total
_PESOS = {
    "estructura_mga": 0.30,
    "alineacion_plan": 0.30,
    "analisis_estrategico": 0.20,
    "calificacion_sgr": 0.20,
}

_CUADRANTE_LABELS = {
    "OPTIMO": "Óptimo — proceder con formulación MGA completa",
    "BIEN_JUSTIFICADO": "Bien justificado — proyecto pertinente, reformular secciones MGA",
    "ATRACTIVO_CON_RIESGO": "Atractivo con riesgo — incluir en Plan de Desarrollo primero",
    "REFORMULAR": "Reformular — requiere rediseño completo del proyecto",
}

_SEMAFORO = [
    (0.70, "verde",    "Alta viabilidad — listo para gestión SGR"),
    (0.45, "amarillo", "Viabilidad media — atender recomendaciones antes de radicar"),
    (0.0,  "rojo",     "Baja viabilidad — reformulación necesaria"),
]


def _load_prompt() -> str:
    global _PROMPT_TEMPLATE
    if _PROMPT_TEMPLATE is None:
        _PROMPT_TEMPLATE = _PROMPT_PATH.read_text(encoding="utf-8")
    return _PROMPT_TEMPLATE


def _parse_dimension(xml: str, dim_id: str) -> dict[str, Any] | None:
    """Extrae score, nivel, hallazgos y recomendaciones de un bloque <dimension id='...'/>."""
    pattern = rf'<dimension\s+id="{dim_id}">(.*?)</dimension>'
    match = re.search(pattern, xml, re.DOTALL)
    if not match:
        return None
    bloque = match.group(1)

    def _tag(tag: str) -> str:
        m = re.search(rf"<{tag}>(.*?)</{tag}>", bloque, re.DOTALL)
        return m.group(1).strip() if m else ""

    score_raw = _tag("score")
    try:
        score = round(float(score_raw), 4)
    except ValueError:
        score = 0.0

    hallazgos_raw = _tag("hallazgos")
    hallazgos = [h.strip() for h in hallazgos_raw.split(";") if h.strip()]

    recs_raw = _tag("recomendaciones")
    recomendaciones = [r.strip() for r in recs_raw.split(";") if r.strip()]

    nivel = _tag("nivel").lower()
    if nivel not in ("alto", "medio", "bajo"):
        nivel = "alto" if score >= 0.70 else ("medio" if score >= 0.45 else "bajo")

    return {
        "nombre": dim_id,
        "score": min(max(score, 0.0), 1.0),
        "nivel": nivel,
        "hallazgos": hallazgos,
        "recomendaciones": recomendaciones,
    }


def _parse_evaluacion_xml(xml: str) -> dict[str, Any]:
    """Parsea el XML de diagnóstico completo del evaluador."""
    result: dict[str, Any] = {}

    # 4 dimensiones
    for dim_id in ("estructura_mga", "alineacion_plan", "analisis_estrategico", "calificacion_sgr"):
        dim = _parse_dimension(xml, dim_id)
        result[dim_id] = dim or {
            "nombre": dim_id,
            "score": 0.0,
            "nivel": "bajo",
            "hallazgos": ["No evaluado"],
            "recomendaciones": [],
        }

    # en_plan
    en_plan_match = re.search(r"<en_plan>(.*?)</en_plan>", xml, re.DOTALL)
    en_plan_raw = en_plan_match.group(1).strip().lower() if en_plan_match else "false"
    result["en_plan"] = en_plan_raw == "true"

    # evidencia_plan
    ev_match = re.search(r"<evidencia_plan>(.*?)</evidencia_plan>", xml, re.DOTALL)
    result["evidencia_plan"] = ev_match.group(1).strip() if ev_match else ""

    # cuadrante
    cq_match = re.search(r"<cuadrante>(.*?)</cuadrante>", xml, re.DOTALL)
    cuadrante_raw = cq_match.group(1).strip().upper() if cq_match else ""
    if cuadrante_raw not in _CUADRANTE_LABELS:
        # Inferir cuadrante desde scores si el LLM devolvió valor inválido
        s_est = result["estructura_mga"]["score"]
        s_ali = result["alineacion_plan"]["score"]
        if s_est >= _UMBRAL_ESTRUCTURA and s_ali >= _UMBRAL_ALINEACION:
            cuadrante_raw = "OPTIMO"
        elif s_est < _UMBRAL_ESTRUCTURA and s_ali >= _UMBRAL_ALINEACION:
            cuadrante_raw = "BIEN_JUSTIFICADO"
        elif s_est >= _UMBRAL_ESTRUCTURA and s_ali < _UMBRAL_ALINEACION:
            cuadrante_raw = "ATRACTIVO_CON_RIESGO"
        else:
            cuadrante_raw = "REFORMULAR"
    result["cuadrante"] = cuadrante_raw

    # acuerdo_concejo
    ac_match = re.search(r"<acuerdo_concejo>(.*?)</acuerdo_concejo>", xml, re.DOTALL)
    texto_acuerdo = ac_match.group(1).strip() if ac_match else ""
    result["acuerdo_concejo"] = None if texto_acuerdo in ("NO_APLICA", "") else texto_acuerdo

    return result


def _calcular_score_total(dims: dict[str, dict]) -> float:
    total = sum(
        dims[dim_id]["score"] * peso
        for dim_id, peso in _PESOS.items()
        if dim_id in dims
    )
    return round(total, 4)


def _semaforo(score: float) -> tuple[str, str]:
    for umbral, color, label in _SEMAFORO:
        if score >= umbral:
            return color, label
    return "rojo", "Baja viabilidad"


async def evaluar_proyecto(
    *,
    texto_proyecto: str,
    plan_chunks: list[str],
    datos_municipio: dict[str, Any],
    http: httpx.AsyncClient,
    settings: Settings,
) -> dict[str, Any]:
    """
    Diagnóstico inverso de un proyecto SGR existente.

    Args:
        texto_proyecto: texto libre o descripción del proyecto a evaluar
        plan_chunks: fragmentos relevantes del plan de desarrollo (RAG)
        datos_municipio: dict con {divipola, nombre_municipio, categoria_municipio, nbi, icld}
        http: cliente httpx compartido
        settings: configuración de la app

    Returns:
        dict con diagnóstico completo: 4 dimensiones, cuadrante, en_plan, acuerdo_concejo,
        score_total, semaforo, semaforo_label
    """
    prompt_template = _load_prompt()

    municipio_ctx = (
        f"Municipio: {datos_municipio.get('nombre_municipio', 'N/D')}\n"
        f"DIVIPOLA: {datos_municipio.get('divipola', 'N/D')}\n"
        f"Categoría: {datos_municipio.get('categoria_municipio', 'N/D')}\n"
        f"NBI: {datos_municipio.get('nbi', 'N/D')}%\n"
        f"ICLD: {datos_municipio.get('icld', 'N/D')} SMMLV"
    )

    plan_ctx = ""
    if plan_chunks:
        fragmentos = "\n---\n".join(plan_chunks[:6])
        plan_ctx = f"\n\n=== EXTRACTOS DEL PLAN DE DESARROLLO ===\n{fragmentos}"

    user_message = (
        f"=== DATOS DEL MUNICIPIO ===\n{municipio_ctx}\n\n"
        f"=== PROYECTO A EVALUAR ===\n{texto_proyecto}"
        f"{plan_ctx}\n\n"
        "Realiza el diagnóstico completo del proyecto en el formato XML indicado."
    )

    messages = [
        {"role": "system", "content": prompt_template},
        {"role": "user", "content": user_message},
    ]

    try:
        raw = await ai_chat(http=http, settings=settings, messages=messages)
    except Exception as exc:
        logger.warning("[agente_evaluador] Error LLM: %s", exc)
        return _fallback_evaluacion(str(exc))

    # Extraer bloque XML
    xml_match = re.search(r"<evaluacion>(.*?)</evaluacion>", raw, re.DOTALL)
    if not xml_match:
        logger.warning("[agente_evaluador] XML no encontrado en respuesta: %r", raw[:300])
        return _fallback_evaluacion("XML no encontrado en respuesta del LLM")

    xml_bloque = f"<evaluacion>{xml_match.group(1)}</evaluacion>"
    parsed = _parse_evaluacion_xml(xml_bloque)

    score_total = _calcular_score_total(parsed)
    color, label = _semaforo(score_total)

    parsed["score_total"] = score_total
    parsed["semaforo"] = color
    parsed["semaforo_label"] = label
    parsed["cuadrante_label"] = _CUADRANTE_LABELS.get(parsed.get("cuadrante", ""), "")
    parsed["necesita_inclusion_plan"] = not parsed.get("en_plan", True)

    # Checklist Concejo si no está en el plan
    if parsed["necesita_inclusion_plan"]:
        parsed["checklist_concejo"] = _generar_checklist_concejo(parsed.get("cuadrante", ""))
    else:
        parsed["checklist_concejo"] = []

    logger.info(
        "[agente_evaluador] score_total=%.2f cuadrante=%s en_plan=%s semaforo=%s",
        score_total,
        parsed.get("cuadrante"),
        parsed.get("en_plan"),
        color,
    )
    return parsed


def _generar_checklist_concejo(cuadrante: str) -> list[str]:
    """Checklist estándar para el sub-flujo de inclusión en el Plan de Desarrollo."""
    base = [
        "Verificar que el Concejo Municipal esté en sesión ordinaria o extraordinaria",
        "Preparar exposición de motivos con justificación técnica del proyecto",
        "Adjuntar ficha técnica preliminar con nombre, objeto, valor estimado y fuente SGR",
        "Verificar que el eje/programa del plan al que se va a incluir esté activo",
        "Solicitar concepto del secretario de planeación municipal",
        "Presentar proyecto de Acuerdo ante el Concejo con al menos 2 debates",
        "Publicar el proyecto de Acuerdo en la Gaceta Municipal 10 días antes del debate",
        "Obtener sanción del Alcalde una vez aprobado",
        "Registrar la modificación en el SIPLAN/DNP",
    ]
    if cuadrante == "ATRACTIVO_CON_RIESGO":
        base.insert(2, "Justificar la pertinencia estratégica aunque no estaba en el plan original")
    return base


def _fallback_evaluacion(razon: str) -> dict[str, Any]:
    dim_fallback = {
        "score": 0.0,
        "nivel": "bajo",
        "hallazgos": [f"Error en evaluación: {razon}"],
        "recomendaciones": ["Evaluar manualmente con el equipo técnico"],
    }
    return {
        "estructura_mga": {**dim_fallback, "nombre": "estructura_mga"},
        "alineacion_plan": {**dim_fallback, "nombre": "alineacion_plan"},
        "analisis_estrategico": {**dim_fallback, "nombre": "analisis_estrategico"},
        "calificacion_sgr": {**dim_fallback, "nombre": "calificacion_sgr"},
        "en_plan": False,
        "evidencia_plan": "",
        "cuadrante": "REFORMULAR",
        "cuadrante_label": _CUADRANTE_LABELS["REFORMULAR"],
        "acuerdo_concejo": None,
        "score_total": 0.0,
        "semaforo": "rojo",
        "semaforo_label": "Error en evaluación automática",
        "necesita_inclusion_plan": True,
        "checklist_concejo": _generar_checklist_concejo("REFORMULAR"),
    }
