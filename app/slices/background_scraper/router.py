"""Endpoints para gestionar la ingesta automática de normativa base."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.dependencies import get_rag_service
from app.slices.auth.dependencies import AdminUser, CurrentUser
from app.slices.background_scraper import descubrimiento
from app.slices.background_scraper import service as bg
from app.slices.background_scraper import territorial
from app.slices.background_scraper.normas_base import NORMAS_BASE, get_normas_by_priority
from app.slices.background_scraper.schemas import (
    BackgroundScraperEstado,
    BackgroundScraperIniciarRequest,
    DescubrirNormasRequest,
    DescubrirNormasResponse,
    NormaTerritorialCreate,
    NormaTerritorialOut,
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
    current_user: CurrentUser,
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
async def cancelar(current_user: CurrentUser) -> BackgroundScraperEstado:
    cancelado = bg.cancel_task()
    if not cancelado:
        raise HTTPException(409, "No hay ningún proceso de ingesta en curso.")
    return bg.get_estado()


@router.get(
    "/estado",
    response_model=BackgroundScraperEstado,
    summary="Estado actual de la ingesta automática",
)
async def estado(current_user: CurrentUser) -> BackgroundScraperEstado:
    return bg.get_estado()


@router.get(
    "/normas-base",
    summary="Listar normas del catálogo base",
    description="Devuelve todas las normas que el sistema intenta indexar, con su prioridad.",
)
async def normas_base(admin: AdminUser, prioridad_max: int = 3) -> list[dict]:
    return [
        {"codigo": cod, "prioridad": pri}
        for cod, pri in NORMAS_BASE
        if pri <= prioridad_max
    ]


# ── Normas territoriales (gestionadas por el admin) ────────────────────────────

@router.get(
    "/normas-territoriales",
    response_model=list[NormaTerritorialOut],
    summary="Listar normas territoriales del indexer",
    description="Normas propias del municipio/departamento que el indexer suma a las nacionales.",
)
async def listar_normas_territoriales(
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> list[NormaTerritorialOut]:
    return await territorial.listar(db)


@router.post(
    "/normas-territoriales",
    response_model=NormaTerritorialOut,
    summary="Agregar una norma territorial al indexer",
    description="Registra una norma propia (acuerdo/ordenanza/decreto local) para indexarla.",
)
async def crear_norma_territorial(
    payload: NormaTerritorialCreate,
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> NormaTerritorialOut:
    if not payload.codigo.strip():
        raise HTTPException(400, "El código de la norma es obligatorio.")
    return await territorial.crear(
        db,
        codigo=payload.codigo,
        territorio=payload.territorio,
        prioridad=payload.prioridad,
        descripcion=payload.descripcion,
    )


@router.delete(
    "/normas-territoriales/{norma_id}",
    summary="Eliminar una norma territorial",
)
async def eliminar_norma_territorial(
    norma_id: str,
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> dict:
    ok = await territorial.eliminar(db, norma_id)
    if not ok:
        raise HTTPException(404, "Norma territorial no encontrada.")
    return {"detail": "eliminada"}


@router.post(
    "/descubrir-normas",
    response_model=DescubrirNormasResponse,
    summary="Descubrir con IA las normas relevantes y agregarlas al indexer",
    description=(
        "La IA propone las normas (nacionales, departamentales, municipales) relevantes "
        "para SGR/regalías y el plan de desarrollo del territorio; las nuevas se registran "
        "como normas territoriales. Luego pueden indexarse con «Indexar normas»."
    ),
)
async def descubrir_normas_endpoint(
    payload: DescubrirNormasRequest,
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    rag: RagService = Depends(get_rag_service),
) -> DescubrirNormasResponse:
    resultado = await descubrimiento.descubrir_y_registrar(
        db,
        http=rag.http,
        settings=settings,
        municipio=payload.municipio,
        departamento=payload.departamento,
        tema=payload.tema or "Sistema General de Regalías (SGR) y planes de desarrollo",
    )
    return DescubrirNormasResponse(**resultado)
