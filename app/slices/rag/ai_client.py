"""
Facade de IA: elige automáticamente el proveedor según la configuración.

Prioridad para chat:
  1. OpenAI     (OPENAI_API_KEY)       — gpt-4o-mini por defecto
  2. OpenRouter (OPENROUTER_API_KEY)   — API compatible con OpenAI
  3. Gemini     (GEMINI_API_KEY)       — google-genai SDK
  4. Ollama                            — modelo local (fallback)

Embeddings siempre usan Ollama (nomic-embed-text, 768 dims).

Uso:
    from app.slices.rag.ai_client import ai_chat, ai_embed, AiError

    text = await ai_chat(http=http, settings=settings, messages=[...])
    vec  = await ai_embed(http=http, settings=settings, text="...")
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)


class AiError(RuntimeError):
    """Error genérico del proveedor de IA activo."""


# ── OpenAI ───────────────────────────────────────────────────────────────────

async def _openai_chat(*, settings: "Settings", messages: list[dict[str, str]], http: httpx.AsyncClient) -> str:
    """Chat vía OpenAI (gpt-4o-mini por defecto). Cobro por uso, sin prepago."""
    url = f"{settings.openai_base_url}/chat/completions"
    payload = {
        "model": settings.openai_chat_model,
        "messages": messages,
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

    t0 = time.monotonic()
    logger.info("[OPENAI][%s] chat in (%d mensajes)", settings.openai_chat_model, len(messages))

    try:
        resp = await http.post(url, json=payload, headers=headers, timeout=httpx.Timeout(120.0))
        resp.raise_for_status()
    except Exception as exc:
        raise AiError(f"Error OpenAI chat: {exc}") from exc

    data = resp.json()
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise AiError(f"OpenAI respuesta inesperada: {data!r}") from exc

    elapsed = time.monotonic() - t0
    logger.info("[OPENAI][%s] chat out (%.1fs, %d chars)", settings.openai_chat_model, elapsed, len(text))
    return text.strip()


# ── OpenRouter ───────────────────────────────────────────────────────────────

async def _openrouter_chat(*, settings: "Settings", messages: list[dict[str, str]], http: httpx.AsyncClient) -> str:
    """Chat vía OpenRouter (API compatible con OpenAI)."""
    url = f"{settings.openrouter_base_url}/chat/completions"
    payload = {
        "model": settings.openrouter_chat_model,
        "messages": messages,
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://gestor-responsabilidades.local",
        "X-Title": "Gestor de Responsabilidades",  # atribución en rankings de OpenRouter
    }

    t0 = time.monotonic()
    logger.info("[OPENROUTER][%s] chat in (%d mensajes)", settings.openrouter_chat_model, len(messages))

    try:
        resp = await http.post(url, json=payload, headers=headers, timeout=httpx.Timeout(120.0))
        resp.raise_for_status()
    except Exception as exc:
        raise AiError(f"Error OpenRouter chat: {exc}") from exc

    data = resp.json()
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise AiError(f"OpenRouter respuesta inesperada: {data!r}") from exc

    elapsed = time.monotonic() - t0
    logger.info("[OPENROUTER][%s] chat out (%.1fs, %d chars)", settings.openrouter_chat_model, elapsed, len(text))
    return text.strip()


# ── Gemini ────────────────────────────────────────────────────────────────────

async def _gemini_chat(*, settings: "Settings", messages: list[dict[str, str]]) -> str:
    """Llama a Gemini generateContent. No necesita httpx propio (usa google-genai)."""
    try:
        from google import genai  # type: ignore[import-untyped]
        from google.genai import types  # type: ignore[import-untyped]
    except ImportError as exc:
        raise AiError(
            "Paquete 'google-genai' no instalado. Agrega 'google-genai' a requirements.txt"
        ) from exc

    client = genai.Client(api_key=settings.gemini_api_key)

    # Convertir roles: system → primer mensaje user con prefijo, luego alternar user/model
    contents: list[types.Content] = []
    system_parts: list[str] = []

    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            system_parts.append(content)
        elif role == "assistant":
            contents.append(types.Content(role="model", parts=[types.Part(text=content)]))
        else:
            contents.append(types.Content(role="user", parts=[types.Part(text=content)]))

    system_instruction = "\n\n".join(system_parts) if system_parts else None

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.2,
    )

    t0 = time.monotonic()
    logger.info("[GEMINI][%s] chat in (%d mensajes)", settings.gemini_chat_model, len(messages))

    try:
        response = await client.aio.models.generate_content(
            model=settings.gemini_chat_model,
            contents=contents,
            config=config,
        )
    except Exception as exc:
        raise AiError(f"Error Gemini generateContent: {exc}") from exc

    elapsed = time.monotonic() - t0
    text = response.text or ""
    if not text:
        raise AiError(f"Gemini devolvió respuesta vacía: {response!r}")

    logger.info("[GEMINI][%s] chat out (%.1fs, %d chars)", settings.gemini_chat_model, elapsed, len(text))
    return text.strip()


async def _gemini_embed(*, settings: "Settings", text: str, http: httpx.AsyncClient) -> list[float]:
    # Llamada directa a la REST API v1 — evita que el SDK agregue prefijos incorrectos
    model = settings.gemini_embedding_model  # gemini-embedding-001 (text-embedding-004 deprecado)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"

    payload = {
        "model": f"models/{model}",
        "content": {"parts": [{"text": text}]},
        "taskType": "RETRIEVAL_DOCUMENT",
    }

    try:
        resp = await http.post(
            url,
            json=payload,
            params={"key": settings.gemini_api_key},
            timeout=httpx.Timeout(30.0),
        )
        resp.raise_for_status()
    except Exception as exc:
        raise AiError(f"Error Gemini embedContent: {exc}") from exc

    data = resp.json()
    values = data.get("embedding", {}).get("values", [])
    if not values:
        raise AiError(f"Gemini devolvió embedding vacío: {data!r}")
    return [float(v) for v in values]


# ── Facade pública ────────────────────────────────────────────────────────────

async def ai_chat(
    *,
    http: httpx.AsyncClient,
    settings: "Settings",
    messages: list[dict[str, str]],
) -> str:
    """
    Chat con el proveedor activo.

    Prioridad: OpenRouter → Gemini → Ollama.
    """
    if settings.use_openai:
        try:
            return await _openai_chat(settings=settings, messages=messages, http=http)
        except AiError:
            raise
        except Exception as exc:
            raise AiError(str(exc)) from exc

    if settings.use_openrouter:
        try:
            return await _openrouter_chat(settings=settings, messages=messages, http=http)
        except AiError:
            raise
        except Exception as exc:
            raise AiError(str(exc)) from exc

    if settings.use_gemini:
        try:
            return await _gemini_chat(settings=settings, messages=messages)
        except AiError:
            raise
        except Exception as exc:
            raise AiError(str(exc)) from exc

    # Ollama
    from app.slices.rag.ollama_client import OllamaError, ollama_chat

    try:
        return await ollama_chat(
            http=http,
            base_url=settings.ollama_base_url,
            model=settings.ollama_chat_model,
            messages=messages,
        )
    except OllamaError as exc:
        raise AiError(str(exc)) from exc


async def ai_embed(
    *,
    http: httpx.AsyncClient,
    settings: "Settings",
    text: str,
) -> list[float]:
    """
    Embedding con el proveedor activo.

    Gemini si GEMINI_API_KEY está definido, Ollama en caso contrario.

    Nota: ambos producen vectores de 768 dimensiones, compatible con Qdrant sin cambios.
    """
    if settings.use_gemini:
        try:
            return await _gemini_embed(settings=settings, text=text, http=http)
        except AiError:
            raise
        except Exception as exc:
            raise AiError(str(exc)) from exc

    # Ollama
    from app.slices.rag.ollama_client import OllamaError, ollama_embed

    try:
        return await ollama_embed(
            http=http,
            base_url=settings.ollama_base_url,
            model=settings.ollama_embedding_model,
            prompt=text,
        )
    except OllamaError as exc:
        raise AiError(str(exc)) from exc
