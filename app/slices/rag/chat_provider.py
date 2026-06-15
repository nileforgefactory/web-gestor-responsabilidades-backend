"""Dispatcher de chat LLM.

Delega en el facade ``ai_chat``, que enruta automáticamente según las API keys
configuradas con prioridad: OpenAI → OpenRouter → Gemini → Ollama.

Se mantiene como capa de compatibilidad para los callers que ya importaban
``chat_llm`` (p. ej. el coordinador de análisis).
"""

import httpx

from app.core.config import Settings
from app.slices.rag.ai_client import ai_chat


async def chat_llm(
    *,
    http: httpx.AsyncClient,
    settings: Settings,
    messages: list[dict[str, str]],
) -> str:
    """Envía un prompt al proveedor LLM activo (OpenAI/OpenRouter/Gemini/Ollama)."""
    return await ai_chat(http=http, settings=settings, messages=messages)
