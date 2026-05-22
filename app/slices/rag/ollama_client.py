"""Cliente HTTP mínimo para la API REST de Ollama (embeddings y chat)."""

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class OllamaError(RuntimeError):
    """Error de respuesta inesperada o vacía desde Ollama."""


async def ollama_embed(
    *,
    http: httpx.AsyncClient,
    base_url: str,
    model: str,
    prompt: str,
) -> list[float]:
    """
    Obtiene el vector de embeddings para un texto.

    Args:
        http: Cliente HTTP reutilizable.
        base_url: URL base del daemon Ollama.
        model: Nombre del modelo (ej. nomic-embed-text).
        prompt: Texto a embeder.

    Returns:
        Lista de floats de dimensión fija del modelo.
    """
    url = base_url.rstrip("/") + "/api/embeddings"
    response = await http.post(url, json={"model": model, "prompt": prompt})
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    embedding = payload.get("embedding")
    if not isinstance(embedding, list) or not embedding:
        raise OllamaError(f"Embedding vacío respuesta={payload!r}")
    return [float(x) for x in embedding]


async def ollama_chat(
    *,
    http: httpx.AsyncClient,
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
) -> str:
    """
    Invoca el endpoint de chat de Ollama (sin streaming).

    Args:
        messages: Lista de dicts con roles ``system`` / ``user`` / ``assistant``.

    Returns:
        Contenido textual de la respuesta del asistente.
    """
    url = base_url.rstrip("/") + "/api/chat"

    # Log del prompt enviado al LLM
    for i, m in enumerate(messages):
        role = m.get("role", "?")
        body = m.get("content", "")
        logger.debug(
            "[OLLAMA][%s] mensaje[%d] rol=%s (%d chars):\n%s",
            model, i, role, len(body), body[:3000]
        )

    t0 = time.monotonic()
    response = await http.post(
        url,
        json={"model": model, "messages": messages, "stream": False},
        timeout=httpx.Timeout(300.0),
    )
    elapsed = time.monotonic() - t0
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    msg = payload.get("message") or {}
    content = msg.get("content") if isinstance(msg, dict) else None
    if not content or not isinstance(content, str):
        raise OllamaError(f"Respuesta chat inválida: {payload!r}")

    result = content.strip()
    logger.debug(
        "[OLLAMA][%s] respuesta (%.1fs, %d chars):\n%s",
        model, elapsed, len(result), result[:3000]
    )
    return result


async def ollama_health(http: httpx.AsyncClient, base_url: str) -> bool:
    """Comprueba si el daemon Ollama responde en ``/api/tags``."""
    url = base_url.rstrip("/") + "/api/tags"
    response = await http.get(url)
    response.raise_for_status()
    data = response.json()
    return isinstance(data, dict) and "models" in data
