"""Agente MGA — genera las 4 secciones de la Ficha MGA Web para un proyecto SGR."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings
from app.slices.rag.ai_client import ai_chat
from app.slices.sgr.instrumento_mga import (
    MODULO_NOMBRE,
    ItemVerificacion,
    PreguntaMGA,
    checklist_evaluable_ia,
    preguntas_por_modulo,
)

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "mga.md"
_PROMPT_TEMPLATE: str | None = None

# Campos MGA que extraemos del XML
_MGA_FIELDS = ("identificacion", "preparacion", "evaluacion", "programacion")

# Sección MGA (campo de la ficha) <-> módulo del instrumento (1-4)
_MODULO_POR_CAMPO = {"identificacion": 1, "preparacion": 2, "evaluacion": 3, "programacion": 4}

_COBERTURA_Q_RE = re.compile(r'<q\s+n="(\d+)"\s+estado="([a-z_]+)"\s*/>')
_ESTADOS_VALIDOS = {"respondida", "parcial", "no_respondida"}

_CHECKLIST_TAG_RE = re.compile(r"<c\s+([^>]*)/>")
_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')


def _construir_preguntas_guia() -> str:
    """Texto con las preguntas clave del instrumento MGA (módulos 1-4), agrupadas
    por sección, para inyectar como contexto guía en el prompt de generación."""
    bloques: list[str] = []
    for modulo in (1, 2, 3, 4):
        preguntas = preguntas_por_modulo(modulo)
        lineas = [f"### {MODULO_NOMBRE[modulo]} (Módulo {modulo})"]
        for p in preguntas:
            lineas.append(f"{p.numero}. {p.pregunta}")
        bloques.append("\n".join(lineas))
    return "\n\n".join(bloques)


def _parsear_cobertura(raw: str) -> list[dict[str, Any]]:
    """Extrae el bloque <cobertura> del XML y lo mapea a la pregunta real
    (número, módulo, texto) para persistir y mostrar alertas en el frontend."""
    match = re.search(r"<cobertura>(.*?)</cobertura>", raw, re.DOTALL)
    if not match:
        return []
    preguntas_por_numero = {p.numero: p for p in _PREGUNTAS_1_A_4}
    cobertura: list[dict[str, Any]] = []
    vistos: set[int] = set()
    for numero_str, estado in _COBERTURA_Q_RE.findall(match.group(1)):
        numero = int(numero_str)
        if numero in vistos or estado not in _ESTADOS_VALIDOS:
            continue
        pregunta = preguntas_por_numero.get(numero)
        if pregunta is None:
            continue
        vistos.add(numero)
        cobertura.append({
            "numero": numero,
            "modulo": pregunta.modulo,
            "pregunta": pregunta.pregunta,
            "estado": estado,
        })
    cobertura.sort(key=lambda c: c["numero"])
    return cobertura


_PREGUNTAS_1_A_4: list[PreguntaMGA] = [
    p for modulo in (1, 2, 3, 4) for p in preguntas_por_modulo(modulo)
]

_CHECKLIST_EVALUABLE: list[ItemVerificacion] = checklist_evaluable_ia()


def _construir_checklist_guia() -> str:
    """Texto con los ítems del checklist final que la IA puede evaluar contra el
    texto generado (excluye ítems sobre soportes físicos o revisión por un par)."""
    return "\n".join(f"{it.numero}. [{it.modulo}] {it.item}" for it in _CHECKLIST_EVALUABLE)


def _parsear_checklist(raw: str) -> list[dict[str, Any]]:
    """Extrae el bloque <checklist> del XML y lo mapea al ítem real para persistir
    y mostrar cumple/no cumple con motivo en el frontend."""
    match = re.search(r"<checklist>(.*?)</checklist>", raw, re.DOTALL)
    if not match:
        return []
    items_por_numero = {it.numero: it for it in _CHECKLIST_EVALUABLE}
    resultado: list[dict[str, Any]] = []
    vistos: set[int] = set()
    for tag_body in _CHECKLIST_TAG_RE.findall(match.group(1)):
        attrs = dict(_ATTR_RE.findall(tag_body))
        numero_str = attrs.get("n")
        cumple_str = attrs.get("cumple")
        if not numero_str or cumple_str not in ("si", "no"):
            continue
        numero = int(numero_str)
        if numero in vistos:
            continue
        item = items_por_numero.get(numero)
        if item is None:
            continue
        vistos.add(numero)
        resultado.append({
            "numero": numero,
            "modulo": item.modulo,
            "item": item.item,
            "cumple": cumple_str == "si",
            "motivo": attrs.get("motivo") or None,
        })
    resultado.sort(key=lambda c: c["numero"])
    return resultado


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

    preguntas_ctx = _construir_preguntas_guia()
    checklist_ctx = _construir_checklist_guia()

    user_message = (
        f"=== MUNICIPIO ===\n{municipio_ctx}\n\n"
        f"=== PROYECTO SGR CANDIDATO ===\n{proyecto_ctx}\n\n"
        f"=== BRECHA DE ORIGEN ===\n{brecha_ctx}"
        f"{plan_ctx}\n\n"
        f"=== PREGUNTAS GUÍA DEL INSTRUMENTO MGA (responde en prosa lo que la información permita) ===\n{preguntas_ctx}\n\n"
        f"=== CHECKLIST DE VERIFICACIÓN FINAL (evalúa cumple/no cumple sobre lo que escribas) ===\n{checklist_ctx}\n\n"
        "Genera la ficha MGA completa para este proyecto en el formato XML indicado, "
        "incluyendo el bloque <cobertura> con TODAS las preguntas guía anteriores y el "
        "bloque <checklist> con TODOS los ítems del checklist anterior."
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
    cobertura = _parsear_cobertura(raw)
    checklist = _parsear_checklist(raw)
    logger.info(
        "[agente_mga] Proyecto %s → %d/4 secciones generadas, %d/%d preguntas cubiertas, "
        "%d/%d ítems de checklist cumplidos",
        proyecto.get("id"),
        campos_completos,
        sum(1 for c in cobertura if c["estado"] == "respondida"),
        len(_PREGUNTAS_1_A_4),
        sum(1 for c in checklist if c["cumple"]),
        len(_CHECKLIST_EVALUABLE),
    )

    return {
        **secciones,
        "campos_completos": campos_completos,
        "modelo_usado": modelo,
        "cobertura_preguntas": cobertura,
        "checklist_verificacion": checklist,
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
        "cobertura_preguntas": [],
        "checklist_verificacion": [],
    }
