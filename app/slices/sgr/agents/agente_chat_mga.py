"""Agente Chat MGA — edición conversacional de una Ficha MGA ya generada."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings
from app.slices.rag.ai_client import ai_chat

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "chat_mga.md"
_PROMPT_TEMPLATE: str | None = None

# Campos MGA que puede devolver el LLM como "cambios"
_MGA_FIELDS = ("identificacion", "preparacion", "evaluacion", "programacion")

_FALLBACK_RESPUESTA = "No pude procesar el cambio solicitado. Intenta reformular tu solicitud."


def _load_prompt() -> str:
    global _PROMPT_TEMPLATE
    if _PROMPT_TEMPLATE is None:
        _PROMPT_TEMPLATE = _PROMPT_PATH.read_text(encoding="utf-8")
    return _PROMPT_TEMPLATE


def _parse_chat_xml(raw: str) -> dict[str, Any] | None:
    """Extrae <respuesta> y las secciones MGA presentes en el XML del LLM.

    Retorna None si no se encuentra <respuesta> (parseo fallido).
    """
    respuesta_match = re.search(r"<respuesta>(.*?)</respuesta>", raw, re.DOTALL)
    if not respuesta_match:
        return None

    respuesta_ia = respuesta_match.group(1).strip()
    cambios: dict[str, str] = {}
    for field in _MGA_FIELDS:
        pattern = rf"<{field}>(.*?)</{field}>"
        match = re.search(pattern, raw, re.DOTALL)
        if match:
            texto = match.group(1).strip()
            if texto:
                cambios[field] = texto

    return {"respuesta_ia": respuesta_ia, "cambios": cambios}


def _formatear_historial(historial: list[dict]) -> str:
    """Formatea los últimos 2-3 turnos previos como contexto simple de conversación."""
    if not historial:
        return ""

    turnos_recientes = historial[-3:]
    lineas: list[str] = []
    for turno in turnos_recientes:
        role = turno.get("role", "usuario")
        texto = turno.get("texto", "")
        etiqueta = "Usuario" if role == "usuario" else "Asistente"
        lineas.append(f"{etiqueta}: {texto}")

    return "\n".join(lineas)


async def chat_editar_ficha(
    *,
    ficha_actual: dict[str, str | None],
    mensaje_usuario: str,
    historial: list[dict],
    http: httpx.AsyncClient,
    settings: Settings,
) -> dict[str, Any]:
    """
    Procesa una solicitud conversacional de edición sobre la Ficha MGA actual.

    Args:
        ficha_actual: dict con {identificacion, preparacion, evaluacion, programacion}
        mensaje_usuario: solicitud del funcionario municipal (ej. "amplía el cronograma")
        historial: turnos previos de chat_historial, puede estar vacío
        http: cliente httpx compartido
        settings: configuración de la app

    Returns:
        dict con {"respuesta_ia": str, "cambios": dict[str, str]} — "cambios" solo trae
        las claves de sección que el LLM decidió modificar (puede estar vacío).
    """
    prompt_template = _load_prompt()

    ficha_ctx = (
        f"=== IDENTIFICACIÓN ACTUAL ===\n{ficha_actual.get('identificacion') or '(sin contenido)'}\n\n"
        f"=== PREPARACIÓN ACTUAL ===\n{ficha_actual.get('preparacion') or '(sin contenido)'}\n\n"
        f"=== EVALUACIÓN ACTUAL ===\n{ficha_actual.get('evaluacion') or '(sin contenido)'}\n\n"
        f"=== PROGRAMACIÓN ACTUAL ===\n{ficha_actual.get('programacion') or '(sin contenido)'}"
    )

    historial_ctx = _formatear_historial(historial)
    historial_bloque = f"\n\n=== CONVERSACIÓN PREVIA ===\n{historial_ctx}" if historial_ctx else ""

    user_message = (
        f"{ficha_ctx}"
        f"{historial_bloque}\n\n"
        f"=== SOLICITUD DEL USUARIO ===\n{mensaje_usuario}\n\n"
        "Analiza la solicitud, decide qué sección(es) deben modificarse y responde "
        "en el formato XML indicado."
    )

    messages = [
        {"role": "system", "content": prompt_template},
        {"role": "user", "content": user_message},
    ]

    try:
        raw = await ai_chat(http=http, settings=settings, messages=messages)
    except Exception as exc:
        logger.warning("[agente_chat_mga] Error LLM: %s", exc)
        return {"respuesta_ia": _FALLBACK_RESPUESTA, "cambios": {}}

    resultado = _parse_chat_xml(raw)
    if resultado is None:
        logger.warning("[agente_chat_mga] XML no parseable: %r", raw[:200])
        return {"respuesta_ia": _FALLBACK_RESPUESTA, "cambios": {}}

    logger.info(
        "[agente_chat_mga] Cambios aplicados: %s",
        list(resultado["cambios"].keys()) or "ninguno",
    )
    return resultado
