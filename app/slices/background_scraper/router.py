"""Endpoints para gestionar la ingesta automática de normativa base."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import Settings, get_settings
from app.dependencies import get_rag_service
from app.slices.background_scraper import service as bg
from app.slices.background_scraper.normas_base import NORMAS_BASE, get_normas_by_priority
from app.slices.background_scraper.schemas import (
    BackgroundScraperEstado,
    BackgroundScraperIniciarRequest,
)
from app.slices.rag.service import RagService

router = APIRouter(prefix="/background-scraper", tags=["background-scraper"])


@router.post(
    "/iniciar",
    response_model=BackgroundScraperEstado,
    summary="Iniciar ingesta automática de normativa base",
    description=(
        "Lanza un proceso en background que busca e indexa las normas colombianas "
        "necesarias para el análisis de planes de desarrollo. "
        "Se detiene al agotar `duracion_min` minutos (default: `BACKGROUND_SCRAPER_DURATION_MIN`). "
        "Si ya hay un proceso corriendo retorna 409."
    ),
)
async def iniciar(
    payload: BackgroundScraperIniciarRequest,
    settings: Settings = Depends(get_settings),
    rag: RagService = Depends(get_rag_service),
) -> BackgroundScraperEstado:
    iniciado = bg.start_background_scraper(
        settings=settings,
        rag=rag,
        duracion_min=payload.duracion_min,
        prioridad_max=payload.prioridad_max,
        pais=payload.pais,
        solo_faltantes=payload.solo_faltantes,
    )
    if not iniciado:
        raise HTTPException(409, "Ya hay un proceso de ingesta en curso. Use /estado para consultarlo.")
    return bg.get_estado()


@router.post(
    "/cancelar",
    response_model=BackgroundScraperEstado,
    summary="Cancelar ingesta en curso",
)
async def cancelar() -> BackgroundScraperEstado:
    cancelado = bg.cancel_task()
    if not cancelado:
        raise HTTPException(409, "No hay ningún proceso de ingesta en curso.")
    return bg.get_estado()


@router.get(
    "/estado",
    response_model=BackgroundScraperEstado,
    summary="Estado actual de la ingesta automática",
)
async def estado() -> BackgroundScraperEstado:
    return bg.get_estado()


@router.get(
    "/normas-base",
    summary="Listar normas del catálogo base",
    description="Devuelve todas las normas que el sistema intenta indexar, con su prioridad.",
)
async def normas_base(prioridad_max: int = 3) -> list[dict]:
    return [
        {"codigo": cod, "prioridad": pri}
        for cod, pri in NORMAS_BASE
        if pri <= prioridad_max
    ]
