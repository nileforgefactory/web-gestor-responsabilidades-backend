"""Cliente para la API de Gemini (solo chat; los embeddings siguen en Ollama)."""

import logging
import time
from typing import Any

import google.generativeai as genai

logger = logging.getLogger(__name__)


class GeminiError(RuntimeError):
    """Error de respuesta inesperada o vacía desde Gemini."""


async def gemini_chat(
    *,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
) -> str:
    """
    Invoca la API de Gemini para generación de texto (sin streaming).

    Convierte el formato ``[{role, content}]`` de Ollama al formato de Gemini:
    system → system_instruction del modelo; user/assistant → contents.

    Args:
        api_key: Clave de API de Google AI Studio.
        model: Nombre del modelo (ej. gemini-2.0-flash).
        messages: Lista de dicts con roles ``system`` / ``user`` / ``assistant``.

    Returns:
        Contenido textual de la respuesta del asistente.
    """
    genai.configure(api_key=api_key)

    system_instruction: str | None = None
    contents: list[dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            system_instruction = content
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": content}]})
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": content}]})

    total_chars = sum(len(m.get("content", "")) for m in messages)
    if logger.isEnabledFor(logging.DEBUG):
        for i, m in enumerate(messages):
            logger.debug(
                "[GEMINI][%s] mensaje[%d] rol=%s (%d chars):\n%s",
                model, i, m.get("role", "?"), len(m.get("content", "")), m.get("content", "")[:3000],
            )
    else:
        logger.info("[GEMINI][%s] chat in (%d mensajes, %d chars)", model, len(messages), total_chars)

    kwargs: dict[str, Any] = {}
    if system_instruction:
        kwargs["system_instruction"] = system_instruction

    model_obj = genai.GenerativeModel(model_name=model, **kwargs)

    t0 = time.monotonic()
    response = await model_obj.generate_content_async(contents)
    elapsed = time.monotonic() - t0

    text = getattr(response, "text", None)
    if not text or not isinstance(text, str):
        raise GeminiError(f"Respuesta Gemini inválida: {response!r}")

    result = text.strip()
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("[GEMINI][%s] respuesta (%.1fs, %d chars):\n%s", model, elapsed, len(result), result[:3000])
    else:
        logger.info("[GEMINI][%s] chat out (%.1fs, %d chars)", model, elapsed, len(result))

    return result
