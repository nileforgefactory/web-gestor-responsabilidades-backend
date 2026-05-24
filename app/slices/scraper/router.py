"""Endpoints HTTP del scraper de normativa."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.core.openapi import RESPUESTAS_RAG
from app.dependencies import get_rag_service
from app.slices.rag.service import RagService
from app.slices.scraper.schemas import ScraperBuscarRequest, ScraperBuscarResponse
from app.slices.scraper.service import ScraperService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scraper", tags=["scraper"])


def _scraper_service(
    settings: Settings = Depends(get_settings),
    rag: RagService = Depends(get_rag_service),
) -> ScraperService:
    return ScraperService(settings=settings, rag=rag)


@router.post(
    "/buscar-normas",
    response_model=ScraperBuscarResponse,
    summary="Buscar normas en red e indexar",
    description=(
        "Por cada referencia normativa (en **paralelo**, límite `SCRAPER_MAX_CONCURRENCY`): "
        "búsqueda en internet, descarga, validación con Ollama e indexación en Qdrant si coincide. "
        "Requiere Ollama y Qdrant listos (`GET /health/ready`). "
        "Catálogo MySQL opcional (`MYSQL_URL`); cada norma usa sesión DB propia."
    ),
    responses=RESPUESTAS_RAG,
)
async def buscar_normas(
    payload: ScraperBuscarRequest,
    service: ScraperService = Depends(_scraper_service),
) -> ScraperBuscarResponse:
    """Ejecuta el flujo completo para todas las normas del cuerpo."""
    logger.info("[SCRAPER] solicitud normas=%d", len(payload.normas))
    return await service.buscar_normas(payload.normas)
