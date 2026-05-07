from functools import lru_cache

from app.core.config import get_settings
from app.slices.rag.service import RagService


@lru_cache
def get_rag_service() -> RagService:
    settings = get_settings()
    return RagService.from_settings(settings)
