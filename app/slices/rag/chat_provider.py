"""Dispatcher de chat LLM: enruta a Gemini o Ollama según configuración."""

import httpx

from app.core.config import Settings
from app.slices.rag.gemini_client import gemini_chat
from app.slices.rag.ollama_client import ollama_chat


async def chat_llm(
    *,
    http: httpx.AsyncClient,
    settings: Settings,
    messages: list[dict[str, str]],
) -> str:
    """
    Envía un prompt al proveedor LLM configurado.

    Si ``use_gemini_chat`` está activo usa la API de Gemini;
    de lo contrario usa Ollama (comportamiento previo).
    """
    if settings.use_gemini_chat:
        if not settings.gemini_api_key:
            raise RuntimeError(
                "use_gemini_chat=true pero GEMINI_API_KEY no está configurada en .env"
            )
        return await gemini_chat(
            api_key=settings.gemini_api_key,
            model=settings.gemini_chat_model,
            messages=messages,
        )

    return await ollama_chat(
        http=http,
        base_url=settings.ollama_base_url,
        model=settings.ollama_chat_model,
        messages=messages,
    )
