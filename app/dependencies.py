"""Dependencias inyectables de FastAPI (servicios singleton)."""

from functools import lru_cache

from app.core.config import get_settings
from app.slices.rag.service import RagService


@lru_cache
def get_rag_service() -> RagService:
    """
    Factory cacheada del servicio RAG.

    Una instancia por proceso; reutiliza cliente Qdrant y HTTP hacia Ollama.
    """
    settings = get_settings()
    return RagService.from_settings(settings)
